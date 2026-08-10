from __future__ import annotations

from dataclasses import dataclass

from ai_governance.ontology import OntologyEntity, OntologyRelationship, OntologyService
from ai_governance.ontology.synchronization.projection import (
    ProjectionFingerprint,
    fingerprint_entities,
    fingerprint_relationships,
)


@dataclass(frozen=True)
class GraphProjectionSnapshot:
    """
    Read-only snapshot of the current ontology graph projection for an entity.

    The snapshot contains the primary entity, relationships attached to the
    primary entity, related endpoint entities, and any persisted reconciliation
    metadata stored on the primary entity. It is the "actual" side of the
    expected-vs-actual comparison performed by diff-based reconciliation.
    """

    primary_entity_type: str
    primary_entity_id: str
    entities: tuple[OntologyEntity, ...]
    relationships: tuple[OntologyRelationship, ...]
    stored_projection_hash: str | None
    stored_relationship_set_hash: str | None
    projection_source: str | None
    projection_version: str | None
    last_synchronized_at: str | None

    @property
    def exists(self) -> bool:
        """
        Return whether the primary entity exists in the current graph.
        """

        return bool(self.entities)

    @property
    def fingerprint(self) -> ProjectionFingerprint:
        """
        Compute semantic fingerprints from current graph state.
        """

        return ProjectionFingerprint(
            projection_hash=fingerprint_entities(self.entities),
            relationship_set_hash=fingerprint_relationships(self.relationships),
        )


class GraphProjectionSnapshotLoader:
    """
    Loads current graph projection state through `OntologyService`.

    The loader stays repository-neutral. Neo4j, in-memory repositories, and
    future graph stores are all accessed through the same ontology service
    methods. The lookup is intentionally centered on the primary entity because
    scoped reconciliation repairs one domain projection at a time.
    """

    def __init__(self, ontology_service: OntologyService) -> None:
        self._ontology_service = ontology_service

    def load(
        self,
        primary_entity_type: str,
        primary_entity_id: str,
    ) -> GraphProjectionSnapshot:
        """
        Load the current projection neighborhood for one primary entity.

        Missing primary entities return an empty snapshot. Existing primary
        entities return their attached relationships and relationship endpoint
        entities, de-duplicated by `(entity_type, entity_id)`.
        """

        primary = self._ontology_service.get_entity(
            primary_entity_type,
            primary_entity_id,
        )
        if primary is None:
            return GraphProjectionSnapshot(
                primary_entity_type=primary_entity_type,
                primary_entity_id=primary_entity_id,
                entities=(),
                relationships=(),
                stored_projection_hash=None,
                stored_relationship_set_hash=None,
                projection_source=None,
                projection_version=None,
                last_synchronized_at=None,
            )

        relationships = tuple(
            sorted(
                self._ontology_service.find_relationships(
                    primary_entity_type,
                    primary_entity_id,
                ),
                key=lambda item: item.relationship_id,
            )
        )
        related_entities = []
        for relationship in relationships:
            for entity_type, entity_id in (
                (
                    relationship.source_entity_type,
                    relationship.source_entity_id,
                ),
                (
                    relationship.target_entity_type,
                    relationship.target_entity_id,
                ),
            ):
                entity = self._ontology_service.get_entity(entity_type, entity_id)
                if entity is not None:
                    related_entities.append(entity)

        entities_by_key = {
            (entity.entity_type, entity.entity_id): entity
            for entity in (primary, *related_entities)
        }
        entities = tuple(
            sorted(
                entities_by_key.values(),
                key=lambda item: (item.entity_type, item.entity_id),
            )
        )
        metadata = primary.metadata
        return GraphProjectionSnapshot(
            primary_entity_type=primary_entity_type,
            primary_entity_id=primary_entity_id,
            entities=entities,
            relationships=relationships,
            stored_projection_hash=_metadata_value(metadata, "projection_hash"),
            stored_relationship_set_hash=_metadata_value(
                metadata,
                "relationship_set_hash",
            ),
            projection_source=_metadata_value(metadata, "projection_source"),
            projection_version=_metadata_value(metadata, "projection_version"),
            last_synchronized_at=_metadata_value(
                metadata,
                "last_synchronized_at",
            ),
        )


def _metadata_value(metadata: object, key: str) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    if isinstance(value, str):
        return value
    return None
