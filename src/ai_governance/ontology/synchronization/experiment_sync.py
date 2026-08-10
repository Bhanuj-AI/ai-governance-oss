from __future__ import annotations

from ai_governance.domain.experiments import Experiment, ExperimentCandidate
from ai_governance.ontology import EntityType, OntologyService, RelationshipType
from ai_governance.ontology.synchronization.synchronizer import (
    BaseOntologySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    provider_entity_id,
    sync_actor,
    sync_relationship,
)
from ai_governance.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from ai_governance.repositories.experiment_repository import ExperimentRepository


class ExperimentOntologySynchronizer(BaseOntologySynchronizer[Experiment]):
    """
    Synchronizes experiment lifecycle metadata into the ontology projection.
    """

    def __init__(
        self,
        ontology_service: OntologyService,
        experiment_repository: ExperimentRepository | None = None,
    ) -> None:
        super().__init__(
            ontology_service,
            source_name="experiment_service",
            loader=(
                experiment_repository.find_by_id
                if experiment_repository is not None
                else None
            ),
        )

    def _synchronize(self, entity: Experiment) -> SynchronizationResult:
        actor_id = sync_actor(self._ontology_service, entity.owner)
        self._ontology_service.create_entity(
            entity_id=entity.experiment_id,
            entity_type=EntityType.EXPERIMENT,
            owner=entity.owner,
            lifecycle=entity.status.value,
            created_at=entity.created_at,
            immutable_attributes={
                "experiment_id": entity.experiment_id,
                "name": entity.name,
                "created_at": entity.created_at.isoformat(),
            },
            mutable_attributes={
                "description": entity.description,
                "owner": entity.owner,
                "status": entity.status.value,
            },
            metadata={"synchronized_from": "experiment_service"},
        )
        relationship_ids = [
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.EXPERIMENT,
                source_id=entity.experiment_id,
                relationship_type=RelationshipType.CREATED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.owner,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.EXPERIMENT,
                source_id=entity.experiment_id,
                relationship_type=RelationshipType.OWNED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.owner,
            ),
        ]
        return SynchronizationResult(
            synchronized_entity_ids=(entity.experiment_id, actor_id),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=2,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(self, entity: Experiment) -> tuple[str, str]:
        return EntityType.EXPERIMENT.value, entity.experiment_id


class CandidateOntologySynchronizer(BaseOntologySynchronizer[ExperimentCandidate]):
    """
    Synchronizes experiment candidates and candidate asset relationships.

    Prompt, model, and dataset version entities must already exist. This keeps
    candidate synchronization one-way and prevents it from fabricating registry
    assets outside their owning services.
    """

    def __init__(
        self,
        ontology_service: OntologyService,
        candidate_repository: ExperimentCandidateRepository | None = None,
    ) -> None:
        super().__init__(
            ontology_service,
            source_name="experiment_candidate_service",
            loader=(
                candidate_repository.find_by_id
                if candidate_repository is not None
                else None
            ),
        )

    def _synchronize(
        self,
        entity: ExperimentCandidate,
    ) -> SynchronizationResult:
        provider_id = provider_entity_id(entity.evaluation_provider)
        self._ontology_service.create_entity(
            entity_id=provider_id,
            entity_type=EntityType.EVALUATION_PROVIDER,
            owner=entity.evaluation_provider,
            lifecycle="AVAILABLE",
            created_at=entity.created_at,
            immutable_attributes={"provider": entity.evaluation_provider},
            metadata={"synchronized_from": "experiment_candidate_service"},
        )
        self._ontology_service.create_entity(
            entity_id=entity.candidate_id,
            entity_type=EntityType.CANDIDATE,
            owner=entity.experiment_id,
            lifecycle="CREATED",
            created_at=entity.created_at,
            immutable_attributes={
                "candidate_id": entity.candidate_id,
                "experiment_id": entity.experiment_id,
                "name": entity.name,
                "prompt_id": entity.prompt_id,
                "prompt_version": entity.prompt_version,
                "model_id": entity.model_id,
                "model_version": entity.model_version,
                "dataset_id": entity.dataset_id,
                "dataset_version": entity.dataset_version,
                "evaluation_provider": entity.evaluation_provider,
                "temperature": entity.temperature,
                "top_p": entity.top_p,
                "max_tokens": entity.max_tokens,
                "metadata": entity.metadata,
            },
            metadata={"synchronized_from": "experiment_candidate_service"},
        )
        relationship_ids = [
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.EXPERIMENT,
                source_id=entity.experiment_id,
                relationship_type=RelationshipType.HAS_CANDIDATE,
                target_type=EntityType.CANDIDATE,
                target_id=entity.candidate_id,
                created_by=entity.experiment_id,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.CANDIDATE,
                source_id=entity.candidate_id,
                relationship_type=RelationshipType.PARTICIPATES_IN,
                target_type=EntityType.EXPERIMENT,
                target_id=entity.experiment_id,
                created_by=entity.experiment_id,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.CANDIDATE,
                source_id=entity.candidate_id,
                relationship_type=RelationshipType.USES,
                target_type=EntityType.PROMPT_VERSION,
                target_id=entity.prompt_id,
                created_by=entity.experiment_id,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.CANDIDATE,
                source_id=entity.candidate_id,
                relationship_type=RelationshipType.USES,
                target_type=EntityType.MODEL_VERSION,
                target_id=entity.model_id,
                created_by=entity.experiment_id,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.CANDIDATE,
                source_id=entity.candidate_id,
                relationship_type=RelationshipType.USES,
                target_type=EntityType.DATASET_VERSION,
                target_id=entity.dataset_id,
                created_by=entity.experiment_id,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.CANDIDATE,
                source_id=entity.candidate_id,
                relationship_type=RelationshipType.EVALUATED_BY,
                target_type=EntityType.EVALUATION_PROVIDER,
                target_id=provider_id,
                created_by=entity.experiment_id,
            ),
        ]
        return SynchronizationResult(
            synchronized_entity_ids=(entity.candidate_id, provider_id),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=2,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(
        self,
        entity: ExperimentCandidate,
    ) -> tuple[str, str]:
        return EntityType.CANDIDATE.value, entity.candidate_id
