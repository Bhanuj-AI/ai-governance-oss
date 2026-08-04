from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, Protocol, TypeVar

from kavach.ontology.enums import EntityType, RelationshipType
from kavach.ontology.models import OntologyEntity, OntologyRelationship

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_DEPTH = 1
MAX_DEPTH = 5
DEFAULT_LIMIT = 100
MAX_LIMIT = 500
DEFAULT_PATH_LIMIT = 10


@dataclass(frozen=True)
class GraphEntity:
    """
    Read-only ontology entity projection for graph query APIs.
    """

    entity_id: str
    entity_type: str
    lifecycle: str
    owner: str
    ontology_version: str
    created_at: datetime
    metadata: Mapping[str, object] = field(default_factory=dict)
    immutable_attributes: Mapping[str, object] = field(default_factory=dict)
    mutable_attributes: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_ontology_entity(cls, entity: OntologyEntity) -> GraphEntity:
        return cls(
            entity_id=entity.entity_id,
            entity_type=entity.entity_type,
            lifecycle=entity.lifecycle,
            owner=entity.owner,
            ontology_version=entity.ontology_version,
            created_at=entity.created_at,
            metadata=dict(entity.metadata),
            immutable_attributes=dict(entity.immutable_attributes),
            mutable_attributes=dict(entity.mutable_attributes),
        )


@dataclass(frozen=True)
class GraphRelationship:
    """
    Read-only ontology relationship projection for graph query APIs.
    """

    relationship_id: str
    relationship_type: str
    source_entity_id: str
    source_entity_type: str
    target_entity_id: str
    target_entity_type: str
    ontology_version: str
    created_at: datetime
    created_by: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_ontology_relationship(
        cls,
        relationship: OntologyRelationship,
    ) -> GraphRelationship:
        return cls(
            relationship_id=relationship.relationship_id,
            relationship_type=relationship.relationship_type,
            source_entity_id=relationship.source_entity_id,
            source_entity_type=relationship.source_entity_type,
            target_entity_id=relationship.target_entity_id,
            target_entity_type=relationship.target_entity_type,
            ontology_version=relationship.ontology_version,
            created_at=relationship.created_at,
            created_by=relationship.created_by,
            metadata=dict(relationship.metadata),
        )


@dataclass(frozen=True)
class GraphNode:
    """
    Node in a returned graph subgraph or path.
    """

    entity: GraphEntity
    depth: int = 0


@dataclass(frozen=True)
class GraphEdge:
    """
    Directed edge in a returned graph subgraph or path.
    """

    relationship: GraphRelationship


@dataclass(frozen=True)
class GraphSubgraph:
    """
    Bounded graph query result containing nodes and edges.
    """

    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()


@dataclass(frozen=True)
class GraphPath:
    """
    Ordered graph path between two ontology entities.
    """

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


@dataclass(frozen=True)
class GraphQueryPage(Generic[T]):
    """
    Cursor-paginated graph query result.
    """

    items: tuple[T, ...]
    limit: int
    next_cursor: str | None = None


@dataclass(frozen=True)
class GraphQueryFilters:
    """
    Common filters accepted by graph query APIs.
    """

    direction: str | None = None
    relationship_types: tuple[str, ...] = ()
    entity_types: tuple[str, ...] = ()
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None


class OntologyGraphQueryRepository(Protocol):
    """
    Read-only repository abstraction for ontology graph queries.
    """

    def get_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> GraphEntity | None: ...

    def get_relationship(
        self,
        relationship_id: str,
    ) -> GraphRelationship | None: ...

    def find_relationships(
        self,
        entity_type: str,
        entity_id: str,
        direction: str | None = None,
        relationship_type: str | None = None,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> GraphQueryPage[GraphRelationship]: ...

    def get_neighbourhood(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = DEFAULT_DEPTH,
        relationship_types: Sequence[str] | None = None,
        entity_types: Sequence[str] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> GraphSubgraph: ...

    def get_upstream(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = DEFAULT_DEPTH,
        relationship_types: Sequence[str] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> GraphSubgraph: ...

    def get_downstream(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = DEFAULT_DEPTH,
        relationship_types: Sequence[str] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> GraphSubgraph: ...

    def find_paths(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        max_depth: int = MAX_DEPTH,
        relationship_types: Sequence[str] | None = None,
        limit: int = DEFAULT_PATH_LIMIT,
    ) -> list[GraphPath]: ...


class OntologyGraphQueryService:
    """
    Validating read-only facade for graph query APIs.
    """

    def __init__(
        self,
        repository: OntologyGraphQueryRepository,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._repository = repository
        self._logger = logger or LOGGER

    def get_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> GraphEntity | None:
        entity_type = _validate_entity_type(entity_type)
        return self._record_query(
            "get_entity",
            lambda: self._repository.get_entity(entity_type, entity_id),
        )

    def get_relationship(
        self,
        relationship_id: str,
    ) -> GraphRelationship | None:
        return self._record_query(
            "get_relationship",
            lambda: self._repository.get_relationship(relationship_id),
        )

    def find_relationships(
        self,
        entity_type: str,
        entity_id: str,
        *,
        direction: str | None = None,
        relationship_type: str | None = None,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> GraphQueryPage[GraphRelationship]:
        entity_type = _validate_entity_type(entity_type)
        direction = _validate_direction(direction)
        relationship_type = _validate_optional_relationship_type(relationship_type)
        limit = _validate_limit(limit)
        return self._record_query(
            "find_relationships",
            lambda: self._repository.find_relationships(
                entity_type,
                entity_id,
                direction=direction,
                relationship_type=relationship_type,
                limit=limit,
                cursor=cursor,
            ),
        )

    def get_neighbourhood(
        self,
        entity_type: str,
        entity_id: str,
        *,
        depth: int = DEFAULT_DEPTH,
        relationship_types: Sequence[str] | None = None,
        entity_types: Sequence[str] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> GraphSubgraph:
        entity_type = _validate_entity_type(entity_type)
        depth = _validate_depth(depth)
        relationship_types = _validate_relationship_types(relationship_types)
        entity_types = _validate_entity_types(entity_types)
        limit = _validate_limit(limit)
        return self._record_query(
            "get_neighbourhood",
            lambda: self._repository.get_neighbourhood(
                entity_type,
                entity_id,
                depth=depth,
                relationship_types=relationship_types,
                entity_types=entity_types,
                limit=limit,
            ),
        )

    def get_upstream_lineage(
        self,
        entity_type: str,
        entity_id: str,
        *,
        depth: int = DEFAULT_DEPTH,
        relationship_types: Sequence[str] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> GraphSubgraph:
        entity_type = _validate_entity_type(entity_type)
        depth = _validate_depth(depth)
        relationship_types = _validate_relationship_types(relationship_types)
        limit = _validate_limit(limit)
        return self._record_query(
            "get_upstream_lineage",
            lambda: self._repository.get_upstream(
                entity_type,
                entity_id,
                depth=depth,
                relationship_types=relationship_types,
                limit=limit,
            ),
        )

    def get_downstream_impact(
        self,
        entity_type: str,
        entity_id: str,
        *,
        depth: int = DEFAULT_DEPTH,
        relationship_types: Sequence[str] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> GraphSubgraph:
        entity_type = _validate_entity_type(entity_type)
        depth = _validate_depth(depth)
        relationship_types = _validate_relationship_types(relationship_types)
        limit = _validate_limit(limit)
        return self._record_query(
            "get_downstream_impact",
            lambda: self._repository.get_downstream(
                entity_type,
                entity_id,
                depth=depth,
                relationship_types=relationship_types,
                limit=limit,
            ),
        )

    def find_paths(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        *,
        max_depth: int = MAX_DEPTH,
        relationship_types: Sequence[str] | None = None,
        limit: int = DEFAULT_PATH_LIMIT,
    ) -> list[GraphPath]:
        source_type = _validate_entity_type(source_type)
        target_type = _validate_entity_type(target_type)
        max_depth = _validate_depth(max_depth)
        relationship_types = _validate_relationship_types(relationship_types)
        limit = _validate_limit(limit)
        return self._record_query(
            "find_paths",
            lambda: self._repository.find_paths(
                source_type,
                source_id,
                target_type,
                target_id,
                max_depth=max_depth,
                relationship_types=relationship_types,
                limit=limit,
            ),
        )

    def _record_query(self, operation: str, query: Callable[[], T]) -> T:
        started = time.perf_counter()
        try:
            return query()
        finally:
            self._logger.info(
                "ontology_graph_query",
                extra={
                    "operation": operation,
                    "duration_ms": round(
                        (time.perf_counter() - started) * 1000,
                        3,
                    ),
                },
            )


def page_items(
    items: Sequence[T],
    *,
    limit: int,
    cursor: str | None,
) -> GraphQueryPage[T]:
    offset = _decode_cursor(cursor)
    page = tuple(items[offset : offset + limit])
    next_offset = offset + len(page)
    next_cursor = str(next_offset) if next_offset < len(items) else None
    return GraphQueryPage(items=page, limit=limit, next_cursor=next_cursor)


def relationship_type_set(
    relationship_types: Iterable[str] | None,
) -> set[str]:
    return set(_validate_relationship_types(tuple(relationship_types or ())))


def entity_type_set(entity_types: Iterable[str] | None) -> set[str]:
    return set(_validate_entity_types(tuple(entity_types or ())))


def _validate_entity_type(value: str) -> str:
    try:
        return EntityType(value).value
    except ValueError as exc:
        raise ValueError(f"Unknown ontology entity type: {value!r}.") from exc


def _validate_optional_relationship_type(value: str | None) -> str | None:
    if value is None:
        return None
    return _validate_relationship_type(value)


def _validate_relationship_type(value: str) -> str:
    try:
        return RelationshipType(value).value
    except ValueError as exc:
        raise ValueError(f"Unknown ontology relationship type: {value!r}.") from exc


def _validate_relationship_types(
    values: Sequence[str] | None,
) -> tuple[str, ...]:
    return tuple(_validate_relationship_type(value) for value in values or ())


def _validate_entity_types(values: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(_validate_entity_type(value) for value in values or ())


def _validate_depth(value: int) -> int:
    if not 1 <= value <= MAX_DEPTH:
        raise ValueError(f"depth must be between 1 and {MAX_DEPTH}.")
    return value


def _validate_limit(value: int) -> int:
    if not 1 <= value <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}.")
    return value


def _validate_direction(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.lower()
    if normalized not in {"incoming", "outgoing", "both"}:
        raise ValueError("direction must be incoming, outgoing, or both.")
    return normalized


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        offset = int(cursor)
    except ValueError as exc:
        raise ValueError("cursor must be an integer offset.") from exc
    if offset < 0:
        raise ValueError("cursor must not be negative.")
    return offset
