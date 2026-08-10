from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ai_governance.ontology.enums import (
    ONTOLOGY_VERSION,
    EntityType,
    EventType,
    RelationshipType,
)
from ai_governance.ontology.exceptions import (
    InvalidOntologyEntityError,
    InvalidOntologyRelationshipError,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _require_non_empty(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty.")


def _coerce_entity_type(value: str | EntityType) -> str:
    try:
        return EntityType(value).value
    except ValueError as exc:
        raise InvalidOntologyEntityError(
            f"Unknown ontology entity type: {value!r}."
        ) from exc


def _coerce_relationship_type(value: str | RelationshipType) -> str:
    try:
        return RelationshipType(value).value
    except ValueError as exc:
        raise InvalidOntologyRelationshipError(
            f"Unknown ontology relationship type: {value!r}."
        ) from exc


def _coerce_event_type(value: str | EventType) -> str:
    try:
        return EventType(value).value
    except ValueError as exc:
        raise ValueError(f"Unknown ontology event type: {value!r}.") from exc


def _copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return dict(value)


@dataclass(frozen=True)
class OntologyEntity:
    """
    Storage-independent representation of one governance ontology entity.

    The entity model captures the minimum semantic fields required by the
    ontology contract. Domain-specific objects such as prompts, models, jobs,
    and audit records are projected into this generic shape by future sync
    workflows; they are not coupled to any graph database API here.
    """

    entity_id: str
    entity_type: str | EntityType
    owner: str
    lifecycle: str
    created_at: datetime = field(default_factory=_now)
    ontology_version: str = ONTOLOGY_VERSION
    immutable_attributes: Mapping[str, Any] = field(default_factory=dict)
    mutable_attributes: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    organization_id: str = "org_default"
    project_id: str = "project_default"
    is_deleted: bool = False
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_empty("entity_id", self.entity_id)
        _require_non_empty("owner", self.owner)
        _require_non_empty("lifecycle", self.lifecycle)
        _require_non_empty("ontology_version", self.ontology_version)
        _require_non_empty("organization_id", self.organization_id)
        _require_non_empty("project_id", self.project_id)

        object.__setattr__(
            self,
            "entity_type",
            _coerce_entity_type(self.entity_type),
        )
        object.__setattr__(
            self,
            "immutable_attributes",
            _copy_mapping(self.immutable_attributes),
        )
        object.__setattr__(
            self,
            "mutable_attributes",
            _copy_mapping(self.mutable_attributes),
        )
        object.__setattr__(self, "metadata", _copy_mapping(self.metadata))


@dataclass(frozen=True)
class OntologyRelationship:
    """
    Directed ontology relationship between two ontology entities.

    Relationship direction is part of the semantic contract and is read as
    `source RELATIONSHIP target`. The model stores source and target entity
    types alongside IDs so validation and repository code do not need to look
    up endpoints simply to understand the relationship shape.
    """

    relationship_type: str | RelationshipType
    source_entity_id: str
    source_entity_type: str | EntityType
    target_entity_id: str
    target_entity_type: str | EntityType
    created_by: str
    relationship_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=_now)
    ontology_version: str = ONTOLOGY_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)
    organization_id: str = "org_default"
    project_id: str = "project_default"
    is_deleted: bool = False
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_empty("relationship_id", self.relationship_id)
        _require_non_empty("source_entity_id", self.source_entity_id)
        _require_non_empty("target_entity_id", self.target_entity_id)
        _require_non_empty("created_by", self.created_by)
        _require_non_empty("ontology_version", self.ontology_version)
        _require_non_empty("organization_id", self.organization_id)
        _require_non_empty("project_id", self.project_id)

        object.__setattr__(
            self,
            "relationship_type",
            _coerce_relationship_type(self.relationship_type),
        )
        object.__setattr__(
            self,
            "source_entity_type",
            _coerce_entity_type(self.source_entity_type),
        )
        object.__setattr__(
            self,
            "target_entity_type",
            _coerce_entity_type(self.target_entity_type),
        )
        object.__setattr__(self, "metadata", _copy_mapping(self.metadata))


@dataclass(frozen=True)
class OntologyEvent:
    """
    Semantic event record associated with an ontology entity.

    Events describe temporal facts such as creation, activation, evaluation
    completion, and report generation. They are intentionally not modeled as
    graph edges because high-volume event streams should not redefine the
    stable decision topology.
    """

    event_type: str | EventType
    entity_id: str
    entity_type: str | EntityType
    actor: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=_now)
    context: Mapping[str, Any] = field(default_factory=dict)
    ontology_version: str = ONTOLOGY_VERSION

    def __post_init__(self) -> None:
        _require_non_empty("event_id", self.event_id)
        _require_non_empty("entity_id", self.entity_id)
        _require_non_empty("actor", self.actor)
        _require_non_empty("ontology_version", self.ontology_version)

        object.__setattr__(
            self,
            "event_type",
            _coerce_event_type(self.event_type),
        )
        object.__setattr__(
            self,
            "entity_type",
            _coerce_entity_type(self.entity_type),
        )
        object.__setattr__(self, "context", _copy_mapping(self.context))
