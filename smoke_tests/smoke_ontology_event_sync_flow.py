from __future__ import annotations

from datetime import UTC, datetime

from kavach.domain.prompts import Prompt, PromptStatus
from kavach.ontology import InMemoryOntologyGraphRepository, OntologyService
from kavach.ontology.synchronization import (
    DiffBasedOntologyReconciler,
    DiffRepositorySynchronizer,
    OntologySyncEventPublisher,
    OntologySynchronizationWorker,
    PromptOntologySynchronizer,
)
from kavach.repositories import InMemoryOntologySyncEventRepository
from kavach.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)


def main() -> None:
    prompt_repository = InMemoryPromptRepository()
    event_repository = InMemoryOntologySyncEventRepository()
    ontology_service = OntologyService(InMemoryOntologyGraphRepository())
    publisher = OntologySyncEventPublisher(event_repository)

    prompt = Prompt(
        prompt_id="prompt-event-1",
        name="support-response",
        version="v1",
        template="Answer the support question: {question}",
        variables=("question",),
        created_at=datetime(2026, 6, 30, tzinfo=UTC),
        created_by="governance-admin",
        status=PromptStatus.ACTIVE,
    )
    prompt_repository.save(prompt)
    event = publisher.publish_entity_event(
        "PromptVersionRegistered",
        entity_type="PromptVersion",
        entity_id=prompt.prompt_id,
        scope_identifier="prompt_registry",
        payload={"prompt_id": prompt.prompt_id},
    )
    print("Published ontology sync event:")
    print(f"  event_id={event.event_id}")
    print(f"  status={event.status.value}")

    prompt_synchronizer = PromptOntologySynchronizer(
        ontology_service,
        prompt_repository,
    )
    reconciler = DiffBasedOntologyReconciler(
        ontology_service,
        synchronizers=(
            DiffRepositorySynchronizer(
                synchronizer=prompt_synchronizer,
                list_entities=prompt_repository.find_all,
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
    worker = OntologySynchronizationWorker(
        event_repository,
        reconciler,
        worker_id="smoke-worker",
    )

    processed = worker.process_next()
    print("Processed ontology sync event:")
    print(f"  status={processed.status.value if processed else 'none'}")
    print(
        "  metrics="
        f"{dict(processed.reconciliation_report) if processed and processed.reconciliation_report else {}}"
    )

    duplicate = publisher.publish_entity_event(
        "PromptVersionRegistered",
        entity_type="PromptVersion",
        entity_id=prompt.prompt_id,
        scope_identifier="prompt_registry",
        payload={"prompt_id": prompt.prompt_id, "duplicate": True},
    )
    skipped = worker.process_next()
    print("Processed duplicate event:")
    print(f"  event_id={duplicate.event_id}")
    print(f"  status={skipped.status.value if skipped else 'none'}")
    print(
        "  metrics="
        f"{dict(skipped.reconciliation_report) if skipped and skipped.reconciliation_report else {}}"
    )


if __name__ == "__main__":
    main()
