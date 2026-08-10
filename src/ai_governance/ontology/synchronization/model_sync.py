from __future__ import annotations

from ai_governance.domain.models import Model
from ai_governance.ontology import EntityType, OntologyService, RelationshipType
from ai_governance.ontology.synchronization.synchronizer import (
    BaseOntologySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    logical_model_id,
    sync_actor,
    sync_relationship,
)
from ai_governance.repositories.model_repository import ModelRepository


class ModelOntologySynchronizer(BaseOntologySynchronizer[Model]):
    """
    Synchronizes governed model versions into the ontology projection.
    """

    def __init__(
        self,
        ontology_service: OntologyService,
        model_repository: ModelRepository | None = None,
    ) -> None:
        super().__init__(
            ontology_service,
            source_name="model_registry",
            loader=(
                model_repository.find_by_id if model_repository is not None else None
            ),
        )
        self._model_repository = model_repository

    def _synchronize(self, entity: Model) -> SynchronizationResult:
        logical_id = logical_model_id(entity.provider, entity.model_name)
        actor_id = sync_actor(self._ontology_service, entity.creator)

        self._ontology_service.create_entity(
            entity_id=logical_id,
            entity_type=EntityType.MODEL,
            owner=entity.creator,
            lifecycle=entity.status.value,
            created_at=entity.created_at,
            immutable_attributes={
                "provider": entity.provider,
                "model_name": entity.model_name,
            },
            mutable_attributes={"status": entity.status.value},
            metadata={
                "synchronized_from": "model_registry",
                "provenance": entity.provenance.value,
                "source_system": entity.source_system,
                "source_reference": entity.source_reference,
            },
        )
        self._ontology_service.create_entity(
            entity_id=entity.model_id,
            entity_type=EntityType.MODEL_VERSION,
            owner=entity.creator,
            lifecycle=entity.status.value,
            created_at=entity.created_at,
            immutable_attributes={
                "model_id": entity.model_id,
                "provider": entity.provider,
                "model_name": entity.model_name,
                "version": entity.version,
                "parameters": entity.parameters,
                "cost": entity.cost,
                "latency": entity.latency,
                "context_window": entity.context_window,
                "creator": entity.creator,
            },
            mutable_attributes={"status": entity.status.value},
            metadata={
                "synchronized_from": "model_registry",
                "provenance": entity.provenance.value,
                "source_system": entity.source_system,
                "source_reference": entity.source_reference,
            },
        )

        relationship_ids = [
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.MODEL,
                source_id=logical_id,
                relationship_type=RelationshipType.HAS_VERSION,
                target_type=EntityType.MODEL_VERSION,
                target_id=entity.model_id,
                created_by=entity.creator,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.MODEL_VERSION,
                source_id=entity.model_id,
                relationship_type=RelationshipType.VERSION_OF,
                target_type=EntityType.MODEL,
                target_id=logical_id,
                created_by=entity.creator,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.MODEL_VERSION,
                source_id=entity.model_id,
                relationship_type=RelationshipType.CREATED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.creator,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.MODEL_VERSION,
                source_id=entity.model_id,
                relationship_type=RelationshipType.OWNED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.creator,
            ),
        ]
        supersedes_id = self._sync_supersedes(entity)
        if supersedes_id is not None:
            relationship_ids.append(supersedes_id)

        return SynchronizationResult(
            synchronized_entity_ids=(logical_id, entity.model_id, actor_id),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=3,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(self, entity: Model) -> tuple[str, str]:
        return EntityType.MODEL_VERSION.value, entity.model_id

    def _sync_supersedes(self, entity: Model) -> str | None:
        if self._model_repository is None:
            return None
        versions = sorted(
            self._model_repository.find_by_logical_model(
                entity.provider,
                entity.model_name,
            ),
            key=lambda item: (item.created_at, item.version, item.model_id),
        )
        previous: Model | None = None
        for model in versions:
            if model.model_id == entity.model_id:
                break
            previous = model
        if previous is None:
            return None
        return sync_relationship(
            self._ontology_service,
            source_type=EntityType.MODEL_VERSION,
            source_id=entity.model_id,
            relationship_type=RelationshipType.SUPERSEDES,
            target_type=EntityType.MODEL_VERSION,
            target_id=previous.model_id,
            created_by=entity.creator,
        )
