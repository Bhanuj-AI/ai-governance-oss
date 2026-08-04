from __future__ import annotations

from kavach.domain.datasets import Dataset
from kavach.ontology import EntityType, OntologyService, RelationshipType
from kavach.ontology.synchronization.synchronizer import (
    BaseOntologySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    logical_dataset_id,
    sync_actor,
    sync_relationship,
)
from kavach.repositories.dataset_repository import DatasetRepository


class DatasetOntologySynchronizer(BaseOntologySynchronizer[Dataset]):
    """
    Synchronizes governed dataset versions into the ontology projection.
    """

    def __init__(
        self,
        ontology_service: OntologyService,
        dataset_repository: DatasetRepository | None = None,
    ) -> None:
        super().__init__(
            ontology_service,
            source_name="dataset_registry",
            loader=(
                dataset_repository.find_by_id
                if dataset_repository is not None
                else None
            ),
        )
        self._dataset_repository = dataset_repository

    def _synchronize(self, entity: Dataset) -> SynchronizationResult:
        logical_id = logical_dataset_id(entity.name)
        actor_id = sync_actor(self._ontology_service, entity.creator)

        self._ontology_service.create_entity(
            entity_id=logical_id,
            entity_type=EntityType.DATASET,
            owner=entity.creator,
            lifecycle=entity.status.value,
            created_at=entity.created_at,
            immutable_attributes={"name": entity.name},
            mutable_attributes={"status": entity.status.value},
            metadata={
                "synchronized_from": "dataset_registry",
                "provenance": entity.provenance.value,
                "source_system": entity.source_system,
                "source_reference": entity.source_reference,
            },
        )
        self._ontology_service.create_entity(
            entity_id=entity.dataset_id,
            entity_type=EntityType.DATASET_VERSION,
            owner=entity.creator,
            lifecycle=entity.status.value,
            created_at=entity.created_at,
            immutable_attributes={
                "dataset_id": entity.dataset_id,
                "name": entity.name,
                "version": entity.version,
                "description": entity.description,
                "storage_uri": entity.storage_uri,
                "storage_type": entity.storage_type,
                "schema_version": entity.schema_version,
                "record_count": entity.record_count,
                "checksum": entity.checksum,
                "creator": entity.creator,
            },
            mutable_attributes={"status": entity.status.value},
            metadata={
                "synchronized_from": "dataset_registry",
                "provenance": entity.provenance.value,
                "source_system": entity.source_system,
                "source_reference": entity.source_reference,
            },
        )

        relationship_ids = [
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.DATASET,
                source_id=logical_id,
                relationship_type=RelationshipType.HAS_VERSION,
                target_type=EntityType.DATASET_VERSION,
                target_id=entity.dataset_id,
                created_by=entity.creator,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.DATASET_VERSION,
                source_id=entity.dataset_id,
                relationship_type=RelationshipType.VERSION_OF,
                target_type=EntityType.DATASET,
                target_id=logical_id,
                created_by=entity.creator,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.DATASET_VERSION,
                source_id=entity.dataset_id,
                relationship_type=RelationshipType.CREATED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.creator,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.DATASET_VERSION,
                source_id=entity.dataset_id,
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
            synchronized_entity_ids=(logical_id, entity.dataset_id, actor_id),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=3,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(self, entity: Dataset) -> tuple[str, str]:
        return EntityType.DATASET_VERSION.value, entity.dataset_id

    def _sync_supersedes(self, entity: Dataset) -> str | None:
        if self._dataset_repository is None:
            return None
        versions = sorted(
            self._dataset_repository.find_by_name(entity.name),
            key=lambda item: (item.created_at, item.version, item.dataset_id),
        )
        previous: Dataset | None = None
        for dataset in versions:
            if dataset.dataset_id == entity.dataset_id:
                break
            previous = dataset
        if previous is None:
            return None
        return sync_relationship(
            self._ontology_service,
            source_type=EntityType.DATASET_VERSION,
            source_id=entity.dataset_id,
            relationship_type=RelationshipType.SUPERSEDES,
            target_type=EntityType.DATASET_VERSION,
            target_id=previous.dataset_id,
            created_by=entity.creator,
        )
