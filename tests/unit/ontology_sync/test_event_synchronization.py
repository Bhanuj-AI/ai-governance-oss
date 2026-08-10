from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import get_ontology_sync_event_service
from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.ontology import InMemoryOntologyGraphRepository, OntologyService
from ai_governance.ontology.synchronization import (
    DiffBasedOntologyReconciler,
    DiffRepositorySynchronizer,
    OntologySyncEvent,
    OntologySyncEventFilter,
    OntologySyncEventPublisher,
    OntologySyncEventService,
    OntologySyncEventStatus,
    OntologySyncProcessingError,
    OntologySyncRetryPolicy,
    OntologySynchronizationWorker,
    PromptOntologySynchronizer,
)
from ai_governance.repositories import (
    InMemoryOntologySyncEventRepository,
    SQLiteOntologySyncEventRepository,
)
from ai_governance.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)
from ai_governance.services.prompts import PromptRegistryService


def test_event_publisher_records_pending_entity_event() -> None:
    repository = InMemoryOntologySyncEventRepository()
    publisher = OntologySyncEventPublisher(
        repository,
        id_generator=_sequence("event-1", "correlation-1"),
        clock=lambda: _now(),
    )

    event = publisher.publish_entity_event(
        "PromptVersionRegistered",
        entity_type="PromptVersion",
        entity_id="prompt-1",
        scope_identifier="prompt_registry",
        payload={"source": "unit-test"},
    )

    stored = repository.find_by_id(event.event_id)
    assert stored is not None
    assert stored.status == OntologySyncEventStatus.PENDING
    assert stored.correlation_id == "correlation-1"
    assert stored.payload == {"source": "unit-test"}


def test_worker_processes_event_through_diff_reconciler() -> None:
    event_repository = InMemoryOntologySyncEventRepository()
    prompt_repository = InMemoryPromptRepository()
    prompt_repository.save(_prompt("prompt-1"))
    reconciler = _prompt_reconciler(
        OntologyService(InMemoryOntologyGraphRepository()),
        prompt_repository,
    )
    event_repository.save(
        OntologySyncEvent(
            event_id="event-1",
            event_type="PromptVersionRegistered",
            entity_type="PromptVersion",
            entity_id="prompt-1",
            scope_identifier="prompt_registry",
            correlation_id="correlation-1",
            created_at=_now(),
            updated_at=_now(),
        )
    )

    processed = OntologySynchronizationWorker(
        event_repository,
        reconciler,
        clock=lambda: _now(),
    ).process_next()

    assert processed is not None
    assert processed.status == OntologySyncEventStatus.COMPLETED
    assert processed.reconciliation_report is not None
    assert processed.reconciliation_report["entities_scanned"] == 1
    assert processed.reconciliation_report["entities_repaired"] == 1


def test_worker_retries_then_dead_letters_retryable_failures() -> None:
    now = _now()
    event_repository = InMemoryOntologySyncEventRepository()
    event_repository.save(
        OntologySyncEvent(
            event_id="event-1",
            event_type="PromptVersionRegistered",
            entity_type="PromptVersion",
            entity_id="prompt-1",
            correlation_id="correlation-1",
            created_at=now,
            updated_at=now,
        )
    )
    clock_values = iter(
        [
            now,
            now,
            now + timedelta(seconds=1),
            now + timedelta(seconds=1),
        ]
    )
    worker = OntologySynchronizationWorker(
        event_repository,
        _FailingReconciler(),
        retry_policy=OntologySyncRetryPolicy(
            max_retries=1,
            base_delay_seconds=1,
        ),
        clock=lambda: next(clock_values),
    )

    failed = worker.process_next()
    dead_letter = worker.process_next()

    assert failed is not None
    assert failed.status == OntologySyncEventStatus.FAILED
    assert failed.retry_count == 1
    assert failed.next_retry_at == now + timedelta(seconds=1)
    assert dead_letter is not None
    assert dead_letter.status == OntologySyncEventStatus.DEAD_LETTER
    assert dead_letter.retry_count == 2


def test_sqlite_event_repository_persists_events(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "ai_governance.db")
    database.initialize()
    repository = SQLiteOntologySyncEventRepository(database)
    repository.save(
        OntologySyncEvent(
            event_id="event-1",
            event_type="PromptVersionRegistered",
            entity_type="PromptVersion",
            entity_id="prompt-1",
            correlation_id="correlation-1",
            payload={"source": "sqlite"},
            created_at=_now(),
            updated_at=_now(),
        )
    )

    reopened = SQLiteOntologySyncEventRepository(database)
    stored = reopened.find_by_id("event-1")

    assert stored is not None
    assert stored.event_type == "PromptVersionRegistered"
    assert stored.payload == {"source": "sqlite"}


def test_rest_event_status_api_lists_retries_cancels_and_reports_metrics() -> None:
    repository = InMemoryOntologySyncEventRepository()
    service = OntologySyncEventService(repository, clock=lambda: _now())
    repository.save(
        OntologySyncEvent(
            event_id="pending-event",
            event_type="PromptVersionRegistered",
            entity_type="PromptVersion",
            entity_id="prompt-1",
            correlation_id="correlation-1",
            created_at=_now(),
            updated_at=_now(),
        )
    )
    repository.save(
        OntologySyncEvent(
            event_id="failed-event",
            event_type="PromptVersionRegistered",
            entity_type="PromptVersion",
            entity_id="prompt-2",
            correlation_id="correlation-2",
            status=OntologySyncEventStatus.FAILED,
            error_message="failed",
            created_at=_now(),
            updated_at=_now(),
        )
    )
    app = create_app()
    app.dependency_overrides[get_ontology_sync_event_service] = lambda: service
    client = TestClient(app)

    listed = client.get(
        "/api/v1/ontology/synchronization/events",
        params={"status": "PENDING"},
    )
    metrics = client.get("/api/v1/ontology/synchronization/events/metrics")
    retried = client.post(
        "/api/v1/ontology/synchronization/events/failed-event/retry"
    )
    cancelled = client.post(
        "/api/v1/ontology/synchronization/events/pending-event/cancel"
    )

    assert listed.status_code == 200
    assert listed.json()["events"][0]["event_id"] == "pending-event"
    assert metrics.status_code == 200
    assert metrics.json()["failed_events"] == 1
    assert retried.status_code == 200
    assert retried.json()["status"] == "PENDING"
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"


def test_prompt_registry_service_publishes_sync_event() -> None:
    event_repository = InMemoryOntologySyncEventRepository()
    prompt_repository = InMemoryPromptRepository()
    service = PromptRegistryService(
        prompt_repository,
        id_generator=_sequence("prompt-1", "event-1", "correlation-1"),
        clock=lambda: _now(),
        ontology_event_publisher=OntologySyncEventPublisher(
            event_repository,
            id_generator=_sequence("event-1", "correlation-1"),
            clock=lambda: _now(),
        ),
    )

    prompt = service.create_prompt(
        name="support",
        version="v1",
        template="Hello",
        variables=(),
        created_by="owner",
    )
    events = event_repository.list_events(
        OntologySyncEventFilter(entity_id=prompt.prompt_id)
    )

    assert len(events) == 1
    assert events[0].event_type == "PromptVersionRegistered"
    assert events[0].entity_type == "PromptVersion"
    assert events[0].scope_identifier == "prompt_registry"


class _FailingReconciler:
    def reconcile_entity(self, entity_type: str, entity_id: str) -> None:
        raise OntologySyncProcessingError("temporary failure")


def _prompt(prompt_id: str) -> Prompt:
    return Prompt(
        prompt_id=prompt_id,
        name="support",
        version="v1",
        template="Hello",
        variables=(),
        created_at=_now(),
        created_by="owner",
        status=PromptStatus.ACTIVE,
    )


def _prompt_reconciler(
    service: OntologyService,
    repository: InMemoryPromptRepository,
) -> DiffBasedOntologyReconciler:
    synchronizer = PromptOntologySynchronizer(service, repository)
    return DiffBasedOntologyReconciler(
        service,
        synchronizers=(
            DiffRepositorySynchronizer(
                synchronizer=synchronizer,
                list_entities=repository.find_all,
                primary_entity_resolver=lambda item: (
                    "PromptVersion",
                    item.prompt_id,
                ),
                projection_source="prompt_registry",
                scope_identifier="prompt_registry",
                entity_type="PromptVersion",
                entity_id_resolver=lambda item: item.prompt_id,
            ),
        ),
    )


def _now() -> datetime:
    return datetime(2026, 6, 30, tzinfo=UTC)


def _sequence(*values: str):
    iterator = iter(values)
    return lambda: next(iterator)
