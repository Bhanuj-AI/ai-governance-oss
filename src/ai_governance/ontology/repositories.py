from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

from ai_governance.ontology.models import OntologyEntity, OntologyRelationship
from ai_governance.ontology.query import (
    DEFAULT_DEPTH,
    DEFAULT_LIMIT,
    DEFAULT_PATH_LIMIT,
    MAX_DEPTH,
    GraphEdge,
    GraphEntity,
    GraphNode,
    GraphPath,
    GraphQueryPage,
    GraphRelationship,
    GraphSubgraph,
    OntologyGraphQueryRepository,
    entity_type_set,
    page_items,
    relationship_type_set,
)


class OntologyGraphRepository(Protocol):
    """
    Storage-independent repository contract for ontology graph persistence.

    Service and caller code depend on this protocol instead of a graph database
    driver. Implementations may use Neo4j, another graph store, or an in-memory
    repository for tests as long as they preserve the same entity and
    relationship semantics.
    """

    def save_entity(self, entity: OntologyEntity) -> OntologyEntity:
        """
        Create or replace an ontology entity.
        """

    def get_entity(
        self,
        entity_type: str,
        entity_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologyEntity | None:
        """
        Return one ontology entity by type and ID.
        """

    def delete_entity(
        self,
        entity_type: str,
        entity_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> None:
        """
        Tombstone an entity while preserving graph history.
        """

    def save_relationship(
        self,
        relationship: OntologyRelationship,
    ) -> OntologyRelationship:
        """
        Create or replace a directed ontology relationship.
        """

    def get_relationship(
        self,
        relationship_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologyRelationship | None:
        """
        Return one ontology relationship by relationship ID.
        """

    def delete_relationship(
        self,
        relationship_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> None:
        """
        Tombstone a relationship while preserving graph history.
        """

    def find_upstream(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 1,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[OntologyEntity]:
        """
        Return entities that can reach the requested entity by outgoing edges.
        """

    def find_downstream(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 1,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[OntologyEntity]:
        """
        Return entities reachable from the requested entity by outgoing edges.
        """

    def find_neighbors(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 1,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[OntologyEntity]:
        """
        Return upstream and downstream entities within the requested depth.
        """

    def find_relationships(
        self,
        entity_type: str,
        entity_id: str,
        direction: str | None = None,
        relationship_type: str | None = None,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[OntologyRelationship]:
        """
        Return relationships connected to an entity with optional filters.
        """


class InMemoryOntologyGraphRepository:
    """
    Deterministic in-memory ontology graph repository for unit tests.

    The repository implements the same contract as the graph adapter while
    keeping traversal behavior simple and dependency-free. It is useful for
    ontology service tests and for local experiments that should not start a
    Neo4j server.
    """

    def __init__(self) -> None:
        self._entities: dict[tuple[str, str, str, str], OntologyEntity] = {}
        self._relationships: dict[tuple[str, str, str], OntologyRelationship] = {}

    def save_entity(self, entity: OntologyEntity) -> OntologyEntity:
        self._entities[
            (
                entity.organization_id,
                entity.project_id,
                entity.entity_type,
                entity.entity_id,
            )
        ] = entity
        return entity

    def get_entity(
        self,
        entity_type: str,
        entity_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologyEntity | None:
        return self._entities.get((organization_id, project_id, entity_type, entity_id))

    def delete_entity(
        self,
        entity_type: str,
        entity_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> None:
        key = (organization_id, project_id, entity_type, entity_id)
        entity = self._entities.get(key)
        if entity is not None:
            self._entities[key] = replace(
                entity,
                lifecycle="ARCHIVED",
                is_deleted=True,
                deleted_at=datetime.now(UTC),
            )

    def save_relationship(
        self,
        relationship: OntologyRelationship,
    ) -> OntologyRelationship:
        self._relationships[
            (
                relationship.organization_id,
                relationship.project_id,
                relationship.relationship_id,
            )
        ] = relationship
        return relationship

    def get_relationship(
        self,
        relationship_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologyRelationship | None:
        return self._relationships.get((organization_id, project_id, relationship_id))

    def delete_relationship(
        self,
        relationship_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> None:
        key = (organization_id, project_id, relationship_id)
        relationship = self._relationships.get(key)
        if relationship is not None:
            self._relationships[key] = replace(
                relationship,
                is_deleted=True,
                deleted_at=datetime.now(UTC),
            )

    def find_upstream(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 1,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[OntologyEntity]:
        return self._traverse(
            entity_type, entity_id, depth, "incoming", organization_id, project_id
        )

    def find_downstream(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 1,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[OntologyEntity]:
        return self._traverse(
            entity_type, entity_id, depth, "outgoing", organization_id, project_id
        )

    def find_neighbors(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 1,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[OntologyEntity]:
        return self._traverse(
            entity_type, entity_id, depth, "both", organization_id, project_id
        )

    def find_relationships(
        self,
        entity_type: str,
        entity_id: str,
        direction: str | None = None,
        relationship_type: str | None = None,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[OntologyRelationship]:
        normalized_direction = _normalize_direction(direction)
        matches = []
        for relationship in self._relationships.values():
            if (relationship.organization_id, relationship.project_id) != (
                organization_id,
                project_id,
            ):
                continue
            if relationship_type is not None and (
                relationship.relationship_type != relationship_type
            ):
                continue
            if relationship.is_deleted:
                continue
            source = self._entities.get(
                (
                    organization_id,
                    project_id,
                    relationship.source_entity_type,
                    relationship.source_entity_id,
                )
            )
            target = self._entities.get(
                (
                    organization_id,
                    project_id,
                    relationship.target_entity_type,
                    relationship.target_entity_id,
                )
            )
            if (
                source is None
                or target is None
                or source.is_deleted
                or target.is_deleted
            ):
                continue
            outgoing = (
                relationship.source_entity_type == entity_type
                and relationship.source_entity_id == entity_id
            )
            incoming = (
                relationship.target_entity_type == entity_type
                and relationship.target_entity_id == entity_id
            )
            if normalized_direction == "outgoing" and outgoing:
                matches.append(relationship)
            elif normalized_direction == "incoming" and incoming:
                matches.append(relationship)
            elif normalized_direction == "both" and (outgoing or incoming):
                matches.append(relationship)

        return sorted(matches, key=lambda item: item.relationship_id)

    def _traverse(
        self,
        entity_type: str,
        entity_id: str,
        depth: int,
        direction: str,
        organization_id: str,
        project_id: str,
    ) -> list[OntologyEntity]:
        if depth < 1:
            return []

        start = (entity_type, entity_id)
        visited = {start}
        found: dict[tuple[str, str], OntologyEntity] = {}
        queue: deque[tuple[tuple[str, str], int]] = deque([(start, 0)])

        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for relationship in self._relationships.values():
                if (relationship.organization_id, relationship.project_id) != (
                    organization_id,
                    project_id,
                ):
                    continue
                if relationship.is_deleted:
                    continue
                next_keys = []
                if (
                    direction in ("outgoing", "both")
                    and (
                        relationship.source_entity_type,
                        relationship.source_entity_id,
                    )
                    == current
                ):
                    next_keys.append(
                        (
                            relationship.target_entity_type,
                            relationship.target_entity_id,
                        )
                    )
                if (
                    direction in ("incoming", "both")
                    and (
                        relationship.target_entity_type,
                        relationship.target_entity_id,
                    )
                    == current
                ):
                    next_keys.append(
                        (
                            relationship.source_entity_type,
                            relationship.source_entity_id,
                        )
                    )
                for next_key in next_keys:
                    if next_key in visited:
                        continue
                    visited.add(next_key)
                    entity = self._entities.get(
                        (organization_id, project_id, *next_key)
                    )
                    if entity is None:
                        continue
                    if entity.is_deleted:
                        continue
                    found[next_key] = entity
                    queue.append((next_key, current_depth + 1))

        return sorted(
            found.values(),
            key=lambda item: (item.entity_type, item.entity_id),
        )


class InMemoryOntologyGraphQueryRepository(OntologyGraphQueryRepository):
    """
    Read-only graph query adapter over an in-memory ontology graph.
    """

    def __init__(
        self,
        graph_repository: InMemoryOntologyGraphRepository,
    ) -> None:
        self._graph_repository = graph_repository

    def get_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> GraphEntity | None:
        entity = self._graph_repository.get_entity(entity_type, entity_id)
        return (
            GraphEntity.from_ontology_entity(entity)
            if entity is not None and not entity.is_deleted
            else None
        )

    def search_entities(
        self,
        query: str,
        entity_types: Sequence[str] | None = None,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> GraphQueryPage[GraphEntity]:
        entity_filter = entity_type_set(entity_types)
        matches = [
            GraphEntity.from_ontology_entity(entity)
            for (organization_id, project_id, _, _), entity in (
                self._graph_repository._entities.items()
            )
            if organization_id == "org_default"
            and project_id == "project_default"
            and not entity.is_deleted
            and (not entity_filter or entity.entity_type in entity_filter)
            and _entity_matches_query(entity, query)
        ]
        matches.sort(
            key=lambda entity: (
                entity.entity_id.casefold() != query.casefold(),
                not entity.entity_id.casefold().startswith(query.casefold()),
                entity.entity_type,
                entity.entity_id,
            )
        )
        return page_items(matches, limit=limit, cursor=cursor)

    def get_relationship(
        self,
        relationship_id: str,
    ) -> GraphRelationship | None:
        relationship = self._graph_repository.get_relationship(relationship_id)
        if relationship is None or relationship.is_deleted:
            return None
        if not self._relationship_endpoints_are_live(relationship):
            return None
        return GraphRelationship.from_ontology_relationship(relationship)

    def find_relationships(
        self,
        entity_type: str,
        entity_id: str,
        direction: str | None = None,
        relationship_type: str | None = None,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> GraphQueryPage[GraphRelationship]:
        relationships = [
            GraphRelationship.from_ontology_relationship(relationship)
            for relationship in self._graph_repository.find_relationships(
                entity_type,
                entity_id,
                direction=direction,
                relationship_type=relationship_type,
            )
        ]
        return page_items(relationships, limit=limit, cursor=cursor)

    def get_neighbourhood(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = DEFAULT_DEPTH,
        relationship_types: Sequence[str] | None = None,
        entity_types: Sequence[str] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> GraphSubgraph:
        return self._subgraph(
            entity_type,
            entity_id,
            depth=depth,
            direction="both",
            relationship_types=relationship_types,
            entity_types=entity_types,
            limit=limit,
        )

    def get_upstream(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = DEFAULT_DEPTH,
        relationship_types: Sequence[str] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> GraphSubgraph:
        return self._subgraph(
            entity_type,
            entity_id,
            depth=depth,
            direction="incoming",
            relationship_types=relationship_types,
            entity_types=None,
            limit=limit,
        )

    def get_downstream(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = DEFAULT_DEPTH,
        relationship_types: Sequence[str] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> GraphSubgraph:
        return self._subgraph(
            entity_type,
            entity_id,
            depth=depth,
            direction="outgoing",
            relationship_types=relationship_types,
            entity_types=None,
            limit=limit,
        )

    def find_paths(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        max_depth: int = MAX_DEPTH,
        relationship_types: Sequence[str] | None = None,
        limit: int = DEFAULT_PATH_LIMIT,
    ) -> list[GraphPath]:
        relationship_filter = relationship_type_set(relationship_types)
        source = (source_type, source_id)
        target = (target_type, target_id)
        if (
            "org_default",
            "project_default",
            *source,
        ) not in self._graph_repository._entities:
            return []
        if (
            "org_default",
            "project_default",
            *target,
        ) not in self._graph_repository._entities:
            return []

        paths: list[GraphPath] = []
        queue: deque[tuple[tuple[str, str], tuple[str, ...]]] = deque([(source, ())])
        while queue and len(paths) < limit:
            current, relationship_path = queue.popleft()
            if len(relationship_path) >= max_depth:
                continue
            for relationship in self._outgoing_relationships(
                current,
                relationship_filter,
            ):
                next_key = (
                    relationship.target_entity_type,
                    relationship.target_entity_id,
                )
                if _path_revisits_node(
                    self._graph_repository,
                    source,
                    relationship_path,
                    next_key,
                ):
                    continue
                next_path = relationship_path + (relationship.relationship_id,)
                if next_key == target:
                    paths.append(self._path_from_relationship_ids(source, next_path))
                    if len(paths) >= limit:
                        break
                else:
                    queue.append((next_key, next_path))
        return paths

    def _subgraph(
        self,
        entity_type: str,
        entity_id: str,
        *,
        depth: int,
        direction: str,
        relationship_types: Sequence[str] | None,
        entity_types: Sequence[str] | None,
        limit: int,
    ) -> GraphSubgraph:
        start = (entity_type, entity_id)
        start_entity = self._graph_repository._entities.get(
            ("org_default", "project_default", *start)
        )
        if start_entity is None or start_entity.is_deleted:
            return GraphSubgraph()

        relationship_filter = relationship_type_set(relationship_types)
        entity_filter = entity_type_set(entity_types)
        nodes: dict[tuple[str, str], GraphNode] = {
            start: GraphNode(GraphEntity.from_ontology_entity(start_entity), 0)
        }
        edges: dict[str, GraphEdge] = {}
        queue: deque[tuple[tuple[str, str], int]] = deque([(start, 0)])

        while queue and len(nodes) < limit:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for relationship in self._matching_relationships(
                current,
                direction,
                relationship_filter,
            ):
                next_key = _other_key(current, relationship)
                entity = self._graph_repository._entities.get(
                    ("org_default", "project_default", *next_key)
                )
                if entity is None:
                    continue
                if entity.is_deleted:
                    continue
                if entity_filter and entity.entity_type not in entity_filter:
                    continue
                edges[relationship.relationship_id] = GraphEdge(
                    GraphRelationship.from_ontology_relationship(relationship)
                )
                if next_key in nodes:
                    continue
                if len(nodes) >= limit:
                    break
                nodes[next_key] = GraphNode(
                    GraphEntity.from_ontology_entity(entity),
                    current_depth + 1,
                )
                queue.append((next_key, current_depth + 1))

        return GraphSubgraph(
            nodes=tuple(
                sorted(
                    nodes.values(),
                    key=lambda node: (
                        node.depth,
                        node.entity.entity_type,
                        node.entity.entity_id,
                    ),
                )
            ),
            edges=tuple(
                sorted(
                    edges.values(),
                    key=lambda edge: edge.relationship.relationship_id,
                )
            ),
        )

    def _matching_relationships(
        self,
        current: tuple[str, str],
        direction: str,
        relationship_filter: set[str],
    ) -> list[OntologyRelationship]:
        matches = []
        for relationship in self._graph_repository._relationships.values():
            if relationship.is_deleted:
                continue
            if (
                relationship_filter
                and relationship.relationship_type not in relationship_filter
            ):
                continue
            source = (
                relationship.source_entity_type,
                relationship.source_entity_id,
            )
            target = (
                relationship.target_entity_type,
                relationship.target_entity_id,
            )
            if direction in {"outgoing", "both"} and source == current:
                if self._relationship_endpoints_are_live(relationship):
                    matches.append(relationship)
            elif direction in {"incoming", "both"} and target == current:
                if self._relationship_endpoints_are_live(relationship):
                    matches.append(relationship)
        return sorted(matches, key=lambda item: item.relationship_id)

    def _relationship_endpoints_are_live(
        self, relationship: OntologyRelationship
    ) -> bool:
        source = self._graph_repository._entities.get(
            (
                relationship.organization_id,
                relationship.project_id,
                relationship.source_entity_type,
                relationship.source_entity_id,
            )
        )
        target = self._graph_repository._entities.get(
            (
                relationship.organization_id,
                relationship.project_id,
                relationship.target_entity_type,
                relationship.target_entity_id,
            )
        )
        return (
            source is not None
            and target is not None
            and not source.is_deleted
            and not target.is_deleted
        )

    def _outgoing_relationships(
        self,
        current: tuple[str, str],
        relationship_filter: set[str],
    ) -> list[OntologyRelationship]:
        return self._matching_relationships(
            current,
            "outgoing",
            relationship_filter,
        )

    def _path_from_relationship_ids(
        self,
        source: tuple[str, str],
        relationship_ids: tuple[str, ...],
    ) -> GraphPath:
        node_keys = [source]
        edges = []
        for relationship_id in relationship_ids:
            relationship = self._graph_repository._relationships[
                ("org_default", "project_default", relationship_id)
            ]
            node_keys.append(
                (
                    relationship.target_entity_type,
                    relationship.target_entity_id,
                )
            )
            edges.append(
                GraphEdge(GraphRelationship.from_ontology_relationship(relationship))
            )
        return GraphPath(
            nodes=tuple(
                GraphNode(
                    GraphEntity.from_ontology_entity(
                        self._graph_repository._entities[
                            ("org_default", "project_default", *node_key)
                        ]
                    ),
                    depth=index,
                )
                for index, node_key in enumerate(node_keys)
            ),
            edges=tuple(edges),
        )


def _entity_matches_query(entity: OntologyEntity, query: str) -> bool:
    needle = query.casefold()
    searchable = (
        entity.entity_id,
        entity.entity_type,
        entity.owner,
        *(_searchable_values(entity.immutable_attributes)),
        *(_searchable_values(entity.mutable_attributes)),
        *(_searchable_values(entity.metadata)),
    )
    return any(needle in value.casefold() for value in searchable)


def _searchable_values(value: object) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        return tuple(
            item for nested in value.values() for item in _searchable_values(nested)
        )
    if isinstance(value, (list, tuple, set)):
        return tuple(item for nested in value for item in _searchable_values(nested))
    return (str(value),)


def _other_key(
    current: tuple[str, str],
    relationship: OntologyRelationship,
) -> tuple[str, str]:
    source = (
        relationship.source_entity_type,
        relationship.source_entity_id,
    )
    if current == source:
        return (
            relationship.target_entity_type,
            relationship.target_entity_id,
        )
    return (
        relationship.source_entity_type,
        relationship.source_entity_id,
    )


def _path_revisits_node(
    repository: InMemoryOntologyGraphRepository,
    source: tuple[str, str],
    relationship_path: tuple[str, ...],
    next_key: tuple[str, str],
) -> bool:
    visited = {source}
    for relationship_id in relationship_path:
        relationship = repository._relationships[
            ("org_default", "project_default", relationship_id)
        ]
        visited.add(
            (
                relationship.target_entity_type,
                relationship.target_entity_id,
            )
        )
    return next_key in visited


def _normalize_direction(direction: str | None) -> str:
    if direction is None:
        return "both"
    normalized = direction.lower()
    if normalized not in {"incoming", "outgoing", "both"}:
        raise ValueError(
            "Relationship direction must be incoming, outgoing, both, or None."
        )
    return normalized
