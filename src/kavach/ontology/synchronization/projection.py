from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kavach.ontology import OntologyEntity, OntologyRelationship
from kavach.ontology.enums import ONTOLOGY_VERSION
from kavach.ontology.models import _now
from kavach.ontology.repositories import InMemoryOntologyGraphRepository
from kavach.ontology.validation import RelationshipValidator

PROJECTION_VERSION = "1.0.0"

IGNORED_METADATA_KEYS = {
    "last_synchronized_at",
    "projection_hash",
    "projection_source",
    "projection_version",
    "relationship_set_hash",
    "synchronized_from",
}


@dataclass(frozen=True)
class ProjectionFingerprint:
    """
    Deterministic hashes for one ontology projection.

    `projection_hash` covers semantic entity state. `relationship_set_hash`
    covers the unordered semantic relationship set.

    Fingerprints deliberately ignore synchronization bookkeeping such as
    `last_synchronized_at` and stored hash metadata. This lets reconciliation
    answer the governance question "did the semantic projection drift?" without
    being distracted by when the projection was last repaired.
    """

    projection_hash: str
    relationship_set_hash: str


@dataclass(frozen=True)
class OntologyProjection:
    """
    Expected ontology projection generated from domain state.

    A projection is detached from storage. It contains the primary entity, all
    entities a synchronizer would write, all relationships it would create, and
    deterministic fingerprints over the semantic state.

    The primary entity identifies the domain object being reconciled. For
    example, prompt registry reconciliation uses `PromptVersion/prompt-id` as
    the primary entity while the projection may also include the logical
    `Prompt`, `Actor`, and provenance relationships that are required to make
    the graph semantically complete.
    """

    primary_entity_type: str
    primary_entity_id: str
    entities: tuple[OntologyEntity, ...]
    relationships: tuple[OntologyRelationship, ...]
    projection_source: str
    projection_version: str = PROJECTION_VERSION

    @property
    def fingerprint(self) -> ProjectionFingerprint:
        return fingerprint_projection(self)


class RecordingOntologyService:
    """
    OntologyService-shaped recorder used by ProjectionBuilder.

    It captures intended entity and relationship writes without touching a graph
    repository. Relationship validation is preserved, but endpoint existence is
    intentionally not required so builders can produce complete expected
    projections even when the current graph is drifted or missing nodes.

    Seed entities and relationships model the current graph state that a
    synchronizer may inspect before deciding whether to write optional links.
    They are available for reads, but they are not emitted in the expected
    projection unless the synchronizer writes them again. This distinction keeps
    fingerprints scoped to the domain object's expected projection instead of
    accidentally hashing the surrounding graph neighborhood.
    """

    def __init__(
        self,
        seed_entities: tuple[OntologyEntity, ...] = (),
        seed_relationships: tuple[OntologyRelationship, ...] = (),
    ) -> None:
        self._repository = InMemoryOntologyGraphRepository()
        self._validator = RelationshipValidator()
        self._written_entity_keys: set[tuple[str, str]] = set()
        self._written_relationship_ids: set[str] = set()
        for entity in seed_entities:
            self._repository.save_entity(entity)
        for relationship in seed_relationships:
            self._repository.save_relationship(relationship)

    @property
    def entities(self) -> tuple[OntologyEntity, ...]:
        """
        Return only entities written by the synchronizer during recording.
        """

        return tuple(
            sorted(
                (
                    entity
                    for key, entity in self._repository._entities.items()
                    if (entity.entity_type, entity.entity_id)
                    in self._written_entity_keys
                ),
                key=lambda item: (item.entity_type, item.entity_id),
            )
        )

    @property
    def relationships(self) -> tuple[OntologyRelationship, ...]:
        """
        Return only relationships written by the synchronizer during recording.
        """

        return tuple(
            sorted(
                (
                    relationship
                    for relationship in self._repository._relationships.values()
                    if relationship.relationship_id in self._written_relationship_ids
                ),
                key=lambda item: item.relationship_id,
            )
        )

    def create_entity(
        self,
        *,
        entity_id: str,
        entity_type: str,
        owner: str,
        lifecycle: str,
        created_at: datetime | None = None,
        ontology_version: str = ONTOLOGY_VERSION,
        immutable_attributes: Mapping[str, Any] | None = None,
        mutable_attributes: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> OntologyEntity:
        """
        Record an entity write using the same shape as `OntologyService`.
        """

        entity = OntologyEntity(
            entity_id=entity_id,
            entity_type=entity_type,
            owner=owner,
            lifecycle=lifecycle,
            created_at=created_at or _now(),
            ontology_version=ontology_version,
            immutable_attributes=immutable_attributes or {},
            mutable_attributes=mutable_attributes or {},
            metadata=metadata or {},
        )
        self._repository.save_entity(entity)
        self._written_entity_keys.add((entity.entity_type, entity.entity_id))
        return entity

    def save_entity(self, entity: OntologyEntity) -> OntologyEntity:
        """
        Record an already-built entity.
        """

        saved = self._repository.save_entity(entity)
        self._written_entity_keys.add((entity.entity_type, entity.entity_id))
        return saved

    def get_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> OntologyEntity | None:
        return self._repository.get_entity(entity_type, entity_id)

    def create_relationship(
        self,
        *,
        source_type: str,
        source_id: str,
        relationship_type: str,
        target_type: str,
        target_id: str,
        created_by: str = "system",
        relationship_id: str | None = None,
        created_at: datetime | None = None,
        ontology_version: str = ONTOLOGY_VERSION,
        metadata: Mapping[str, Any] | None = None,
    ) -> OntologyRelationship:
        """
        Record a relationship write after validating ontology direction.
        """

        relationship = OntologyRelationship(
            relationship_id=relationship_id or "",
            relationship_type=relationship_type,
            source_entity_id=source_id,
            source_entity_type=source_type,
            target_entity_id=target_id,
            target_entity_type=target_type,
            created_by=created_by,
            created_at=created_at or _now(),
            ontology_version=ontology_version,
            metadata=metadata or {},
        )
        self._validator.validate(relationship)
        self._repository.save_relationship(relationship)
        self._written_relationship_ids.add(relationship.relationship_id)
        return relationship

    def find_relationships(
        self,
        entity_type: str,
        entity_id: str,
        direction: str | None = None,
        relationship_type: str | None = None,
    ) -> list[OntologyRelationship]:
        return self._repository.find_relationships(
            entity_type,
            entity_id,
            direction=direction,
            relationship_type=relationship_type,
        )

    def record_existing_relationship(
        self,
        relationship: OntologyRelationship,
    ) -> None:
        """Include an idempotently reused relationship in the projection."""

        self._written_relationship_ids.add(relationship.relationship_id)


class ProjectionBuilder:
    """
    Builds expected ontology projections by reusing synchronizer logic.

    The builder temporarily points a synchronizer at a recording service, calls
    `synchronize`, and returns the captured writes as an `OntologyProjection`.
    No graph writes are performed.

    This keeps synchronizers and reconciliation honest: there is one projection
    mapping for normal synchronization and diff-based reconciliation. The
    builder is intentionally storage-free, so it can be used in unit tests,
    smoke scripts, and future dry-run tooling.

    Example:

        projection = ProjectionBuilder().build(
            synchronizer=PromptOntologySynchronizer(service, repository),
            entity=prompt,
            primary_entity=("PromptVersion", prompt.prompt_id),
            projection_source="prompt_registry",
        )
    """

    def build(
        self,
        *,
        synchronizer: object,
        entity: object,
        primary_entity: tuple[str, str],
        projection_source: str,
        seed_entities: tuple[OntologyEntity, ...] = (),
        seed_relationships: tuple[OntologyRelationship, ...] = (),
    ) -> OntologyProjection:
        """
        Generate the expected projection for one domain object.

        `seed_entities` and `seed_relationships` may be supplied when a
        synchronizer conditionally creates relationships only if related graph
        nodes already exist. The generated projection still includes only the
        synchronizer's intended writes.
        """

        recorder = RecordingOntologyService(
            seed_entities=seed_entities,
            seed_relationships=seed_relationships,
        )
        original_service = getattr(synchronizer, "_ontology_service")
        try:
            setattr(synchronizer, "_ontology_service", recorder)
            result = synchronizer.synchronize(entity)  # type: ignore[attr-defined]
        finally:
            setattr(synchronizer, "_ontology_service", original_service)

        if not result.succeeded:
            raise ValueError(
                "Could not build ontology projection: " + "; ".join(result.errors)
            )

        primary_entity_type, primary_entity_id = primary_entity
        return OntologyProjection(
            primary_entity_type=primary_entity_type,
            primary_entity_id=primary_entity_id,
            entities=recorder.entities,
            relationships=recorder.relationships,
            projection_source=projection_source,
        )


def fingerprint_projection(
    projection: OntologyProjection,
) -> ProjectionFingerprint:
    """
    Return deterministic semantic fingerprints for a projection.

    Entity and relationship fingerprints are computed independently so
    reconciliation can distinguish node drift from edge drift. Both hashes use
    canonical JSON payloads with sorted keys and normalized collections.
    """

    entity_payload = [
        _semantic_entity_payload(entity) for entity in projection.entities
    ]
    relationship_payload = [
        _semantic_relationship_payload(relationship)
        for relationship in projection.relationships
    ]
    return ProjectionFingerprint(
        projection_hash=_hash_payload(entity_payload),
        relationship_set_hash=_hash_payload(relationship_payload),
    )


def fingerprint_entities(
    entities: tuple[OntologyEntity, ...],
) -> str:
    """
    Hash semantic entity state with deterministic ordering.
    """

    return _hash_payload([_semantic_entity_payload(entity) for entity in entities])


def fingerprint_relationships(
    relationships: tuple[OntologyRelationship, ...],
) -> str:
    """
    Hash semantic relationship state independent of relationship order.
    """

    return _hash_payload(
        [_semantic_relationship_payload(relationship) for relationship in relationships]
    )


def _semantic_entity_payload(entity: OntologyEntity) -> dict[str, Any]:
    return {
        "entity_id": entity.entity_id,
        "entity_type": entity.entity_type,
        "owner": entity.owner,
        "lifecycle": entity.lifecycle,
        "ontology_version": entity.ontology_version,
        "immutable_attributes": _canonical(entity.immutable_attributes),
        "mutable_attributes": _canonical(entity.mutable_attributes),
        "metadata": _semantic_metadata(entity.metadata),
    }


def _semantic_relationship_payload(
    relationship: OntologyRelationship,
) -> dict[str, Any]:
    return {
        "relationship_type": relationship.relationship_type,
        "source_entity_id": relationship.source_entity_id,
        "source_entity_type": relationship.source_entity_type,
        "target_entity_id": relationship.target_entity_id,
        "target_entity_type": relationship.target_entity_type,
        "created_by": relationship.created_by,
        "ontology_version": relationship.ontology_version,
        "metadata": _semantic_metadata(relationship.metadata),
    }


def _semantic_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _canonical(value)
        for key, value in metadata.items()
        if key not in IGNORED_METADATA_KEYS
    }


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _canonical(value[key]) for key in sorted(value.keys(), key=str)}
    if isinstance(value, list | tuple | set):
        return sorted((_canonical(item) for item in value), key=_json)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(_json(_canonical(payload)).encode("utf-8")).hexdigest()


def _json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
