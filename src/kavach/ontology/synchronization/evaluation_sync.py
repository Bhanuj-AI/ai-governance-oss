from __future__ import annotations

from kavach.domain.evaluation_result import EvaluationResult
from kavach.domain.experiments import EvaluationRun
from kavach.ontology import EntityType, OntologyService, RelationshipType
from kavach.ontology.synchronization.synchronizer import (
    BaseOntologySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    artifact_entity_id,
    metric_entity_id,
    provider_entity_id,
    sync_relationship,
)
from kavach.repositories.evaluation_repository import EvaluationRepository
from kavach.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)


class EvaluationRunOntologySynchronizer(BaseOntologySynchronizer[EvaluationRun]):
    """
    Synchronizes experiment evaluation runs into the ontology projection.
    """

    def __init__(
        self,
        ontology_service: OntologyService,
        evaluation_run_repository: EvaluationRunRepository | None = None,
    ) -> None:
        super().__init__(
            ontology_service,
            source_name="evaluation_run_repository",
            loader=(
                evaluation_run_repository.find_by_id
                if evaluation_run_repository is not None
                else None
            ),
        )

    def _synchronize(self, entity: EvaluationRun) -> SynchronizationResult:
        provider_id = provider_entity_id(entity.evaluation_provider)
        self._ontology_service.create_entity(
            entity_id=provider_id,
            entity_type=EntityType.EVALUATION_PROVIDER,
            owner=entity.evaluation_provider,
            lifecycle="AVAILABLE",
            created_at=entity.started_at or entity.completed_at,
            immutable_attributes={"provider": entity.evaluation_provider},
            metadata={"synchronized_from": "evaluation_run_repository"},
        )
        self._ontology_service.create_entity(
            entity_id=entity.run_id,
            entity_type=EntityType.EVALUATION_RUN,
            owner=entity.experiment_id,
            lifecycle=entity.status.value,
            created_at=entity.started_at or entity.completed_at,
            immutable_attributes={
                "run_id": entity.run_id,
                "experiment_id": entity.experiment_id,
                "candidate_id": entity.candidate_id,
                "dataset_version": entity.dataset_version,
                "evaluation_provider": entity.evaluation_provider,
            },
            mutable_attributes={
                "status": entity.status.value,
                "evaluation_result_id": entity.evaluation_result_id,
                "started_at": (
                    entity.started_at.isoformat()
                    if entity.started_at is not None
                    else None
                ),
                "completed_at": (
                    entity.completed_at.isoformat()
                    if entity.completed_at is not None
                    else None
                ),
            },
            metadata={"synchronized_from": "evaluation_run_repository"},
        )

        relationship_ids = [
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.EVALUATION_RUN,
                source_id=entity.run_id,
                relationship_type=RelationshipType.EXECUTES,
                target_type=EntityType.CANDIDATE,
                target_id=entity.candidate_id,
                created_by=entity.experiment_id,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.EVALUATION_RUN,
                source_id=entity.run_id,
                relationship_type=RelationshipType.EVALUATED_BY,
                target_type=EntityType.EVALUATION_PROVIDER,
                target_id=provider_id,
                created_by=entity.experiment_id,
            ),
        ]

        if (
            entity.evaluation_result_id is not None
            and self._ontology_service.get_entity(
                EntityType.EVALUATION_RESULT.value,
                entity.evaluation_result_id,
            )
            is not None
        ):
            relationship_ids.append(
                sync_relationship(
                    self._ontology_service,
                    source_type=EntityType.EVALUATION_RUN,
                    source_id=entity.run_id,
                    relationship_type=RelationshipType.PRODUCES,
                    target_type=EntityType.EVALUATION_RESULT,
                    target_id=entity.evaluation_result_id,
                    created_by=entity.experiment_id,
                )
            )

        return SynchronizationResult(
            synchronized_entity_ids=(entity.run_id, provider_id),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=2,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(self, entity: EvaluationRun) -> tuple[str, str]:
        return EntityType.EVALUATION_RUN.value, entity.run_id


class EvaluationResultOntologySynchronizer(BaseOntologySynchronizer[EvaluationResult]):
    """
    Synchronizes evaluation results, metrics, artifacts, and provider evidence.
    """

    def __init__(
        self,
        ontology_service: OntologyService,
        evaluation_repository: EvaluationRepository | None = None,
    ) -> None:
        super().__init__(
            ontology_service,
            source_name="evaluation_repository",
            loader=(
                evaluation_repository.find_by_evaluation_id
                if evaluation_repository is not None
                else None
            ),
        )

    def _synchronize(
        self,
        entity: EvaluationResult,
    ) -> SynchronizationResult:
        provider_id = provider_entity_id(
            entity.evaluator_type,
            entity.evaluator_version,
        )
        self._ontology_service.create_entity(
            entity_id=provider_id,
            entity_type=EntityType.EVALUATION_PROVIDER,
            owner=entity.evaluator_type,
            lifecycle="AVAILABLE",
            created_at=entity.created_at,
            immutable_attributes={
                "provider": entity.evaluator_type,
                "version": entity.evaluator_version,
                "descriptor_snapshot": entity.provider_descriptor_snapshot,
            },
            metadata={"synchronized_from": "evaluation_repository"},
        )
        self._ontology_service.create_entity(
            entity_id=entity.evaluation_id,
            entity_type=EntityType.EVALUATION_RESULT,
            owner=entity.evaluator_type,
            lifecycle="COMPLETED",
            created_at=entity.created_at,
            immutable_attributes={
                "evaluation_id": entity.evaluation_id,
                "execution_id": entity.execution_id,
                "evaluator_type": entity.evaluator_type,
                "evaluator_version": entity.evaluator_version,
                "provider_metadata": dict(entity.provider_metadata),
            },
            metadata={"synchronized_from": "evaluation_repository"},
        )

        entity_ids = [provider_id, entity.evaluation_id]
        relationship_ids = [
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.EVALUATION_RESULT,
                source_id=entity.evaluation_id,
                relationship_type=RelationshipType.EVALUATED_BY,
                target_type=EntityType.EVALUATION_PROVIDER,
                target_id=provider_id,
                created_by=entity.evaluator_type,
            )
        ]

        for metric in entity.metrics:
            metric_id = metric_entity_id(
                entity.evaluation_id,
                metric.metric_name,
            )
            self._ontology_service.create_entity(
                entity_id=metric_id,
                entity_type=EntityType.METRIC,
                owner=entity.evaluator_type,
                lifecycle="RECORDED",
                created_at=entity.created_at,
                immutable_attributes={
                    "metric_name": metric.metric_name,
                    "metric_value": metric.metric_value,
                    "explanation": metric.explanation,
                },
                metadata={"synchronized_from": "evaluation_repository"},
            )
            entity_ids.append(metric_id)
            relationship_ids.append(
                sync_relationship(
                    self._ontology_service,
                    source_type=EntityType.EVALUATION_RESULT,
                    source_id=entity.evaluation_id,
                    relationship_type=RelationshipType.HAS_METRIC,
                    target_type=EntityType.METRIC,
                    target_id=metric_id,
                    created_by=entity.evaluator_type,
                )
            )

        for index, artifact in enumerate(entity.artifacts):
            artifact_id = artifact_entity_id(entity.evaluation_id, index)
            self._ontology_service.create_entity(
                entity_id=artifact_id,
                entity_type=EntityType.EVALUATION_ARTIFACT,
                owner=entity.evaluator_type,
                lifecycle="RECORDED",
                created_at=entity.created_at,
                immutable_attributes={
                    "artifact_type": artifact.artifact_type,
                    "uri": artifact.uri,
                    "payload": artifact.payload,
                    "metadata": dict(artifact.metadata),
                },
                metadata={"synchronized_from": "evaluation_repository"},
            )
            entity_ids.append(artifact_id)
            relationship_ids.append(
                sync_relationship(
                    self._ontology_service,
                    source_type=EntityType.EVALUATION_RESULT,
                    source_id=entity.evaluation_id,
                    relationship_type=RelationshipType.HAS_ARTIFACT,
                    target_type=EntityType.EVALUATION_ARTIFACT,
                    target_id=artifact_id,
                    created_by=entity.evaluator_type,
                )
            )

        return SynchronizationResult(
            synchronized_entity_ids=tuple(entity_ids),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=len(entity_ids),
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(
        self,
        entity: EvaluationResult,
    ) -> tuple[str, str]:
        return EntityType.EVALUATION_RESULT.value, entity.evaluation_id
