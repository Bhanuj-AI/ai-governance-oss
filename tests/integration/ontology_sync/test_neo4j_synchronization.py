import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.ontology import EntityType, RelationshipType
from ai_governance.ontology.synchronization import (
    DiffBasedOntologyReconciler,
    DiffRepositorySynchronizer,
    GovernanceDecisionOntologySynchronizer,
    GovernanceDecisionProjection,
    OntologySyncEvent,
    OntologySyncEventService,
    OntologySyncEventStatus,
    OntologySyncProcessingError,
    OntologySyncRetryPolicy,
    OntologySynchronizationWorker,
    PromptOntologySynchronizer,
)
from ai_governance.repositories import SQLiteOntologySyncEventRepository
from ai_governance.repositories.in_memory_prompt_repository import InMemoryPromptRepository


def _neo4j_available() -> bool:
    if os.getenv("AI_GOVERNANCE_RUN_NEO4J_TESTS") != "true":
        return False
    try:
        import neo4j  # type: ignore # noqa: F401
    except ImportError:
        return False
    return True


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _neo4j_available(),
        reason=("Set AI_GOVERNANCE_RUN_NEO4J_TESTS=true and install/start Neo4j to run."),
    ),
]


def test_prompt_synchronization_against_neo4j():
    from ai_governance.ontology import OntologyService
    from ai_governance.ontology.neo4j_repository import Neo4jOntologyGraphRepository

    suffix = str(uuid4())
    prompt_id = f"prompt-{suffix}"
    repository = Neo4jOntologyGraphRepository.from_environment()
    try:
        repository.initialize_schema()
        service = OntologyService(repository)
        prompt = Prompt(
            prompt_id=prompt_id,
            name=f"support-{suffix}",
            version="v1",
            template="Hello",
            variables=(),
            created_at=datetime(2026, 6, 30, tzinfo=UTC),
            created_by="integration-test",
            status=PromptStatus.ACTIVE,
        )

        result = PromptOntologySynchronizer(service).synchronize(prompt)

        assert result.succeeded is True
        assert service.get_entity("PromptVersion", prompt_id) is not None
        assert service.find_relationships(
            "PromptVersion",
            prompt_id,
            direction="outgoing",
            relationship_type=RelationshipType.VERSION_OF.value,
        )
    finally:
        repository.close()


def test_governance_decision_metric_evidence_synchronizes_against_neo4j():
    """Guard the worker path that previously dead-lettered Metric evidence."""

    from ai_governance.ontology import OntologyService
    from ai_governance.ontology.neo4j_repository import Neo4jOntologyGraphRepository

    suffix = str(uuid4())
    repository = Neo4jOntologyGraphRepository.from_environment()
    try:
        repository.initialize_schema()
        service = OntologyService(repository)
        candidate_id = f"candidate-{suffix}"
        metric_id = f"metric-{suffix}"
        decision_id = f"decision-{suffix}"
        service.create_entity(
            entity_id=candidate_id,
            entity_type=EntityType.CANDIDATE,
            owner="integration-test",
            lifecycle="CREATED",
        )
        service.create_entity(
            entity_id=metric_id,
            entity_type=EntityType.METRIC,
            owner="integration-test",
            lifecycle="RECORDED",
        )

        result = GovernanceDecisionOntologySynchronizer(service).synchronize(
            GovernanceDecisionProjection(
                decision_id=decision_id,
                decision_type="APPROVE",
                target_entity_type=EntityType.CANDIDATE.value,
                target_entity_id=candidate_id,
                status="APPROVED",
                reason="Metric evidence is accepted by the ontology contract.",
                created_by="integration-test",
                evidence_refs=((EntityType.METRIC.value, metric_id),),
                created_at=datetime(2026, 7, 19, tzinfo=UTC),
            )
        )

        assert result.succeeded is True
        assert service.find_relationships(
            EntityType.GOVERNANCE_DECISION.value,
            decision_id,
            direction="outgoing",
            relationship_type=RelationshipType.GENERATED_FROM.value,
        )
    finally:
        repository.close()


def test_sqlite_event_survives_worker_restart_and_projects_to_neo4j(
    tmp_path: Path,
) -> None:
    """A restarted worker must resume the durable event and repair Neo4j."""

    from ai_governance.ontology import OntologyService
    from ai_governance.ontology.neo4j_repository import Neo4jOntologyGraphRepository

    suffix = str(uuid4())
    prompt = _prompt(f"restart-prompt-{suffix}")
    prompt_repository = InMemoryPromptRepository()
    prompt_repository.save(prompt)
    event_database = SQLiteDatabase(tmp_path / "ontology-sync.db")
    event_database.initialize()
    original_events = SQLiteOntologySyncEventRepository(event_database)
    original_events.save(
        OntologySyncEvent(
            event_id=f"restart-event-{suffix}",
            event_type="PromptVersionRegistered",
            entity_type=EntityType.PROMPT_VERSION.value,
            entity_id=prompt.prompt_id,
            scope_identifier="prompt_registry",
            correlation_id=f"restart-correlation-{suffix}",
        )
    )

    repository = Neo4jOntologyGraphRepository.from_environment()
    try:
        repository.initialize_schema()
        service = OntologyService(repository)
        restarted_events = SQLiteOntologySyncEventRepository(event_database)
        completed = OntologySynchronizationWorker(
            restarted_events,
            _prompt_reconciler(service, prompt_repository),
            worker_id="restarted-worker",
        ).process_next()

        assert completed is not None
        assert completed.status == OntologySyncEventStatus.COMPLETED
        assert restarted_events.find_by_id(completed.event_id) == completed
        assert service.get_entity(EntityType.PROMPT_VERSION.value, prompt.prompt_id)
    finally:
        repository.close()


def test_dead_letter_retry_repairs_projection_in_neo4j(tmp_path: Path) -> None:
    """An operator retry must turn a repaired dead letter into a projection."""

    from ai_governance.ontology import OntologyService
    from ai_governance.ontology.neo4j_repository import Neo4jOntologyGraphRepository

    suffix = str(uuid4())
    prompt = _prompt(f"retry-prompt-{suffix}")
    prompt_repository = InMemoryPromptRepository()
    prompt_repository.save(prompt)
    event_database = SQLiteDatabase(tmp_path / "ontology-sync.db")
    event_database.initialize()
    event_repository = SQLiteOntologySyncEventRepository(event_database)
    event_repository.save(
        OntologySyncEvent(
            event_id=f"retry-event-{suffix}",
            event_type="PromptVersionRegistered",
            entity_type=EntityType.PROMPT_VERSION.value,
            entity_id=prompt.prompt_id,
            scope_identifier="prompt_registry",
            correlation_id=f"retry-correlation-{suffix}",
        )
    )

    dead_letter = OntologySynchronizationWorker(
        event_repository,
        _AlwaysFailingReconciler(),
        retry_policy=OntologySyncRetryPolicy(max_retries=0),
    ).process_next()
    assert dead_letter is not None
    assert dead_letter.status == OntologySyncEventStatus.DEAD_LETTER

    reopened_events = SQLiteOntologySyncEventRepository(event_database)
    retried = OntologySyncEventService(reopened_events).retry_event(
        dead_letter.event_id
    )
    assert retried.status == OntologySyncEventStatus.PENDING

    repository = Neo4jOntologyGraphRepository.from_environment()
    try:
        repository.initialize_schema()
        service = OntologyService(repository)
        completed = OntologySynchronizationWorker(
            reopened_events,
            _prompt_reconciler(service, prompt_repository),
            worker_id="repaired-worker",
        ).process_next()

        assert completed is not None
        assert completed.status == OntologySyncEventStatus.COMPLETED
        assert service.get_entity(EntityType.PROMPT_VERSION.value, prompt.prompt_id)
    finally:
        repository.close()


def _prompt_reconciler(
    service,
    prompt_repository: InMemoryPromptRepository,
) -> DiffBasedOntologyReconciler:
    synchronizer = PromptOntologySynchronizer(service, prompt_repository)
    return DiffBasedOntologyReconciler(
        service,
        synchronizers=(
            DiffRepositorySynchronizer(
                synchronizer=synchronizer,
                list_entities=prompt_repository.find_all,
                primary_entity_resolver=lambda item: (
                    EntityType.PROMPT_VERSION.value,
                    item.prompt_id,
                ),
                projection_source="prompt_registry",
                scope_identifier="prompt_registry",
                entity_type=EntityType.PROMPT_VERSION.value,
                entity_id_resolver=lambda item: item.prompt_id,
            ),
        ),
    )


def _prompt(prompt_id: str) -> Prompt:
    return Prompt(
        prompt_id=prompt_id,
        name=prompt_id,
        version="v1",
        template="Hello",
        variables=(),
        created_at=datetime(2026, 7, 19, tzinfo=UTC),
        created_by="integration-test",
        status=PromptStatus.ACTIVE,
    )


class _AlwaysFailingReconciler:
    def reconcile_entity(self, _entity_type: str, _entity_id: str) -> None:
        raise OntologySyncProcessingError("projection dependency is unavailable")
