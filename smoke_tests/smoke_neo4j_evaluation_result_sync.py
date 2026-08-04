"""Smoke test the targeted EvaluationResult event-to-Neo4j projection flow.

Run after Neo4j is available and schema initialization has completed:
    uv run python smoke_tests/smoke_neo4j_evaluation_result_sync.py
"""

from __future__ import annotations

from datetime import UTC, datetime

from kavach.domain.evaluation_result import EvaluationMetric, EvaluationResult
from kavach.ontology import EntityType, OntologyService
from kavach.ontology.neo4j_repository import Neo4jOntologyGraphRepository
from kavach.ontology.synchronization import (
    DiffBasedOntologyReconciler,
    DiffRepositorySynchronizer,
    EvaluationResultOntologySynchronizer,
    OntologySyncEventPublisher,
    OntologySyncEventStatus,
    OntologySynchronizationWorker,
)
from kavach.repositories import InMemoryOntologySyncEventRepository
from kavach.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)

EVALUATION_ID = "smoke-neo4j-evaluation-result-v1"


def main() -> None:
    graph = Neo4jOntologyGraphRepository.from_environment()
    try:
        graph.initialize_schema()
        evaluations = InMemoryEvaluationRepository()
        result = EvaluationResult(
            evaluation_id=EVALUATION_ID,
            execution_id="smoke-execution-v1",
            evaluator_type="smoke-provider",
            evaluator_version="v1",
            metrics=[EvaluationMetric("answer_relevance", 0.95)],
            created_at=datetime(2026, 7, 19, tzinfo=UTC),
        )
        evaluations.save(result)

        service = OntologyService(graph)
        synchronizer = EvaluationResultOntologySynchronizer(service, evaluations)
        reconciler = DiffBasedOntologyReconciler(
            service,
            synchronizers=(
                DiffRepositorySynchronizer(
                    synchronizer=synchronizer,
                    list_entities=lambda: (),
                    primary_entity_resolver=lambda item: (
                        EntityType.EVALUATION_RESULT.value,
                        item.evaluation_id,
                    ),
                    projection_source="evaluation_repository",
                    scope_identifier="evaluation_repository",
                    entity_type=EntityType.EVALUATION_RESULT.value,
                    entity_id_resolver=lambda item: item.evaluation_id,
                    entity_loader=evaluations.find_by_evaluation_id,
                ),
            ),
        )
        events = InMemoryOntologySyncEventRepository()
        publisher = OntologySyncEventPublisher(events)
        worker = OntologySynchronizationWorker(events, reconciler)

        event = publisher.publish_entity_event(
            "EvaluationCompleted",
            entity_type=EntityType.EVALUATION_RESULT.value,
            entity_id=result.evaluation_id,
            scope_identifier="evaluation_repository",
            payload={"evaluation_id": result.evaluation_id},
        )
        processed = worker.process_next()
        stored = service.get_entity(EntityType.EVALUATION_RESULT.value, EVALUATION_ID)

        assert processed is not None
        assert processed.event_id == event.event_id
        assert processed.status is OntologySyncEventStatus.COMPLETED
        assert stored is not None
        assert stored.immutable_attributes["execution_id"] == "smoke-execution-v1"
        assert service.find_relationships(
            EntityType.EVALUATION_RESULT.value,
            EVALUATION_ID,
            direction="outgoing",
        )

        duplicate = publisher.publish_entity_event(
            "EvaluationCompleted",
            entity_type=EntityType.EVALUATION_RESULT.value,
            entity_id=result.evaluation_id,
            scope_identifier="evaluation_repository",
            payload={"evaluation_id": result.evaluation_id, "redelivered": True},
        )
        replayed = worker.process_next()
        assert replayed is not None
        assert replayed.event_id == duplicate.event_id
        assert replayed.status is OntologySyncEventStatus.COMPLETED
        assert (replayed.reconciliation_report or {})["entities_skipped"] == 1

        print("PASS: EvaluationResult event was targeted, upserted, and idempotent in Neo4j.")
        print(f"  event_id={event.event_id}")
        print(f"  evaluation_id={EVALUATION_ID}")
        print(f"  reconciliation={dict(processed.reconciliation_report or {})}")
    finally:
        graph.close()


if __name__ == "__main__":
    main()
