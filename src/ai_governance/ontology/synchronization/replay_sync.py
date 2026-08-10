from __future__ import annotations

from ai_governance.domain.replay import Replay, ReplayEvaluationHistory, ReplayResult
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.ontology import EntityType, OntologyService, RelationshipType
from ai_governance.ontology.synchronization.synchronizer import (
    BaseOntologySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    sync_relationship,
)


class WorkflowExecutionOntologySynchronizer(
    BaseOntologySynchronizer[WorkflowExecution]
):
    """
    Synchronizes reconstructed workflow executions into the ontology.
    """

    def __init__(self, ontology_service: OntologyService) -> None:
        super().__init__(
            ontology_service,
            source_name="replay_workflow_execution",
        )

    def _synchronize(
        self,
        entity: WorkflowExecution,
    ) -> SynchronizationResult:
        self._ontology_service.create_entity(
            entity_id=entity.execution_id,
            entity_type=EntityType.WORKFLOW_EXECUTION,
            owner=entity.workflow_id,
            lifecycle=entity.execution_status,
            immutable_attributes={
                "workflow_id": entity.workflow_id,
                "execution_id": entity.execution_id,
                "workflow_name": entity.workflow_name,
                "workflow_version": entity.workflow_version,
                "execution_status": entity.execution_status,
                "input": entity.input,
                "final_state": entity.final_state,
                "events": entity.events,
            },
            metadata={"synchronized_from": "replay_service"},
        )
        relationship_ids = [
            relationship_id
            for reference_type, references in (
                (EntityType.PROMPT_VERSION, entity.prompt_refs),
                (EntityType.MODEL_VERSION, entity.model_refs),
                (EntityType.DATASET_VERSION, entity.dataset_refs),
            )
            for reference in references
            if self._ontology_service.get_entity(reference_type.value, reference)
            for relationship_id in (
                sync_relationship(
                    self._ontology_service,
                    source_type=EntityType.WORKFLOW_EXECUTION,
                    source_id=entity.execution_id,
                    relationship_type=RelationshipType.USES,
                    target_type=reference_type,
                    target_id=reference,
                    created_by="replay_service",
                ),
            )
        ]
        return SynchronizationResult(
            synchronized_entity_ids=(entity.execution_id,),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=1,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(
        self,
        entity: WorkflowExecution,
    ) -> tuple[str, str]:
        return EntityType.WORKFLOW_EXECUTION.value, entity.execution_id


class ReplayOntologySynchronizer(BaseOntologySynchronizer[ReplayEvaluationHistory]):
    """
    Synchronizes replay investigations and replay evidence relationships.
    """

    def __init__(self, ontology_service: OntologyService) -> None:
        super().__init__(
            ontology_service,
            source_name="replay_service",
        )

    def _synchronize(
        self,
        entity: ReplayEvaluationHistory,
    ) -> SynchronizationResult:
        replay_id = replay_investigation_id(entity.execution_id)
        self._ontology_service.create_entity(
            entity_id=replay_id,
            entity_type=EntityType.REPLAY_INVESTIGATION,
            owner="replay_service",
            lifecycle="COMPLETED",
            immutable_attributes={
                "execution_id": entity.execution_id,
                "evaluation_count": entity.evaluation_count,
            },
            metadata={"synchronized_from": "replay_service"},
        )

        relationship_ids: list[str] = []
        if self._ontology_service.get_entity(
            EntityType.WORKFLOW_EXECUTION.value,
            entity.execution_id,
        ):
            relationship_ids.extend(
                [
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.REPLAY_INVESTIGATION,
                        source_id=replay_id,
                        relationship_type=RelationshipType.REPLAY_OF,
                        target_type=EntityType.WORKFLOW_EXECUTION,
                        target_id=entity.execution_id,
                        created_by="replay_service",
                    ),
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.REPLAY_INVESTIGATION,
                        source_id=replay_id,
                        relationship_type=RelationshipType.RECONSTRUCTS,
                        target_type=EntityType.WORKFLOW_EXECUTION,
                        target_id=entity.execution_id,
                        created_by="replay_service",
                    ),
                ]
            )

        for record in entity.evaluations:
            if self._ontology_service.get_entity(
                EntityType.EVALUATION_RESULT.value,
                record.evaluation_id,
            ):
                relationship_ids.append(
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.REPLAY_INVESTIGATION,
                        source_id=replay_id,
                        relationship_type=RelationshipType.REPLAY_OF,
                        target_type=EntityType.EVALUATION_RESULT,
                        target_id=record.evaluation_id,
                        created_by="replay_service",
                    )
                )

        return SynchronizationResult(
            synchronized_entity_ids=(replay_id,),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=1,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(
        self,
        entity: ReplayEvaluationHistory,
    ) -> tuple[str, str]:
        return EntityType.REPLAY_INVESTIGATION.value, replay_investigation_id(
            entity.execution_id
        )

    def synchronize_replay(self, replay: Replay) -> SynchronizationResult:
        """Project the production Replay aggregate through OntologyService only."""
        self._ontology_service.create_entity(
            entity_id=replay.replay_id,
            entity_type=EntityType.REPLAY,
            owner=replay.requested_by,
            lifecycle=replay.status.value,
            immutable_attributes={
                "replay_id": replay.replay_id,
                "source_execution_id": replay.source_execution_id,
                "mode": replay.mode.value,
                "configuration_hash": replay.configuration.configuration_hash
                if replay.configuration
                else None,
                "requested_by": replay.requested_by,
                "organization_id": replay.organization_id,
                "project_id": replay.project_id,
                "created_at": replay.created_at.isoformat(),
            },
            metadata={"synchronized_from": "replay_management"},
        )
        relationship_ids: list[str] = []
        for target, relationship in (
            (replay.source_execution_id, RelationshipType.REPLAY_OF),
            (replay.replay_execution_id, RelationshipType.PRODUCES),
            (replay.job_id, RelationshipType.SUBMITTED_AS),
            (replay.evaluation_job_id, RelationshipType.SUBMITTED_AS),
            (replay.baseline_evaluation_id, RelationshipType.GENERATED_FROM),
            (replay.replay_evaluation_id, RelationshipType.PRODUCES),
            (replay.comparison_id, RelationshipType.PRODUCES),
            (replay.drift_id, RelationshipType.CAUSED_DRIFT),
            (replay.result_id, RelationshipType.RESULTED_IN),
        ):
            if target:
                target_type = _replay_target_type(target, relationship)
                if self._ontology_service.get_entity(target_type.value, target):
                    relationship_ids.append(sync_relationship(self._ontology_service, source_type=EntityType.REPLAY, source_id=replay.replay_id, relationship_type=relationship, target_type=target_type, target_id=target, created_by="replay_management"))
        return SynchronizationResult(
            synchronized_entity_ids=(replay.replay_id,),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=1,
                relationships_synchronized=len(relationship_ids),
            ),
        )


class ReplayResultOntologySynchronizer(BaseOntologySynchronizer[ReplayResult]):
    def __init__(self, ontology_service: OntologyService) -> None:
        super().__init__(ontology_service, source_name="replay_result")

    def _synchronize(self, entity: ReplayResult) -> SynchronizationResult:
        self._ontology_service.create_entity(
            entity_id=entity.result_id,
            entity_type=EntityType.REPLAY_RESULT,
            owner="replay_management",
            lifecycle="COMPLETED",
            immutable_attributes={
                "result_id": entity.result_id,
                "replay_id": entity.replay_id,
                "source_execution_id": entity.source_execution_id,
                "replay_execution_id": entity.replay_execution_id,
                "created_at": entity.created_at.isoformat(),
            },
            metadata={"drift_severity": entity.drift_summary.severity},
        )
        return SynchronizationResult(
            synchronized_entity_ids=(entity.result_id,),
            stats=SynchronizationStats(entities_synchronized=1),
        )

    def _archive_target(self, entity: ReplayResult) -> tuple[str, str]:
        return EntityType.REPLAY_RESULT.value, entity.result_id


def _replay_target_type(target: str, relationship: RelationshipType) -> EntityType:
    if relationship is RelationshipType.SUBMITTED_AS:
        return EntityType.JOB
    if relationship is RelationshipType.CAUSED_DRIFT:
        return EntityType.DRIFT_ANALYSIS
    if relationship is RelationshipType.RESULTED_IN:
        return EntityType.REPLAY_RESULT
    if relationship is RelationshipType.PRODUCES and target.startswith("replay-comparison:"):
        return EntityType.EVALUATION_COMPARISON
    if relationship in {RelationshipType.GENERATED_FROM} or target.startswith("baseline"):
        return EntityType.EVALUATION_RESULT
    if relationship is RelationshipType.PRODUCES and target.startswith("replay-evaluation"):
        return EntityType.EVALUATION_RESULT
    return EntityType.WORKFLOW_EXECUTION


def replay_investigation_id(execution_id: str) -> str:
    return f"replay:{execution_id}"
