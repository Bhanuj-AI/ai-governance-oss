from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from kavach.config import (
    KAVACH_GRAPH_DATABASE,
    KAVACH_GRAPH_PASSWORD,
    KAVACH_GRAPH_URI,
    KAVACH_GRAPH_USER,
)
from kavach.ontology.enums import EntityType, RelationshipType
from kavach.ontology.exceptions import (
    MissingNeo4jDriverError,
    OntologyRepositoryError,
)
from kavach.ontology.models import OntologyEntity, OntologyRelationship
from kavach.ontology.query import (
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
    page_items,
)
from kavach.ontology.repositories import _normalize_direction
from kavach.ontology.schema import ONTOLOGY_SCHEMA_CYPHER


class Neo4jOntologyGraphRepository:
    """
    Neo4j-backed implementation of `OntologyGraphRepository`.

    Neo4j driver objects and Cypher details are deliberately isolated in this
    adapter. Domain models and the ontology service remain storage-independent
    and know only about ontology entities, relationships, and traversals.
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        *,
        database: str = "neo4j",
        driver: Any | None = None,
    ) -> None:
        self._database = database
        if driver is not None:
            self._driver = driver
            return

        try:
            from neo4j import GraphDatabase  # type: ignore
        except ImportError as exc:
            raise MissingNeo4jDriverError(
                "The Neo4j Python driver is required for "
                "Neo4jOntologyGraphRepository. Install the `neo4j` package "
                "before using the graph adapter."
            ) from exc

        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    @classmethod
    def from_environment(cls) -> Neo4jOntologyGraphRepository:
        """
        Build a repository from local graph environment variables.
        """

        return cls(
            uri=KAVACH_GRAPH_URI,
            user=KAVACH_GRAPH_USER,
            password=KAVACH_GRAPH_PASSWORD,
            database=KAVACH_GRAPH_DATABASE,
        )

    def close(self) -> None:
        """
        Close the underlying Neo4j driver.
        """

        self._driver.close()

    def initialize_schema(self) -> None:
        """
        Create ontology constraints and indexes.

        Neo4j Community Edition 5.x supports the composite uniqueness
        constraint used here. Older versions may reject it; in that case the
        error should be handled by choosing a supported Neo4j image or by
        adding an equivalent single synthetic key projection in a future
        repository migration.
        """

        with self._session() as session:
            for statement in ONTOLOGY_SCHEMA_CYPHER:
                session.run(statement)

    def save_entity(self, entity: OntologyEntity) -> OntologyEntity:
        label = _safe_entity_label(entity.entity_type)
        properties = _entity_to_properties(entity)
        query = f"""
        MERGE (e:OntologyEntity:{label} {{
            organization_id: $organization_id,
            project_id: $project_id,
            entity_type: $entity_type,
            entity_id: $entity_id
        }})
        SET e += $properties
        RETURN e
        """
        with self._session() as session:
            session.run(
                query,
                organization_id=entity.organization_id,
                project_id=entity.project_id,
                entity_type=entity.entity_type,
                entity_id=entity.entity_id,
                properties=properties,
            )
        return entity

    def get_entity(
        self,
        entity_type: str,
        entity_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologyEntity | None:
        query = """
        MATCH (e:OntologyEntity {organization_id: $organization_id,
              project_id: $project_id, entity_type: $entity_type, entity_id: $entity_id})
        RETURN e
        """
        with self._session() as session:
            record = session.run(
                query,
                organization_id=organization_id,
                project_id=project_id,
                entity_type=entity_type,
                entity_id=entity_id,
            ).single()
        if record is None:
            return None
        return _entity_from_properties(dict(record["e"]))

    def delete_entity(
        self,
        entity_type: str,
        entity_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> None:
        existing = self.get_entity(entity_type, entity_id, organization_id, project_id)
        if existing is not None:
            self.save_entity(
                replace(
                    existing,
                    lifecycle="ARCHIVED",
                    is_deleted=True,
                    deleted_at=datetime.now(UTC),
                )
            )

    def save_relationship(
        self,
        relationship: OntologyRelationship,
    ) -> OntologyRelationship:
        relationship_type = _safe_relationship_type(relationship.relationship_type)
        properties = _relationship_to_properties(relationship)
        query = f"""
        MATCH (source:OntologyEntity {{
            organization_id: $organization_id,
            project_id: $project_id,
            entity_type: $source_entity_type,
            entity_id: $source_entity_id
        }})
        MATCH (target:OntologyEntity {{
            organization_id: $organization_id,
            project_id: $project_id,
            entity_type: $target_entity_type,
            entity_id: $target_entity_id
        }})
        MERGE (source)-[r:{relationship_type} {{
            relationship_id: $relationship_id
        }}]->(target)
        SET r += $properties
        RETURN r
        """
        with self._session() as session:
            result = session.run(
                query,
                organization_id=relationship.organization_id,
                project_id=relationship.project_id,
                source_entity_type=relationship.source_entity_type,
                source_entity_id=relationship.source_entity_id,
                target_entity_type=relationship.target_entity_type,
                target_entity_id=relationship.target_entity_id,
                relationship_id=relationship.relationship_id,
                properties=properties,
            )
            if result.single() is None:
                raise OntologyRepositoryError(
                    "Could not save ontology relationship because one or both "
                    "endpoints were not found."
                )
        return relationship

    def get_relationship(
        self,
        relationship_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologyRelationship | None:
        query = """
        MATCH (source:OntologyEntity {organization_id: $organization_id, project_id: $project_id})
              -[r {relationship_id: $relationship_id}]->
              (target:OntologyEntity {organization_id: $organization_id, project_id: $project_id})
        RETURN source, r, type(r) AS relationship_type, target
        """
        with self._session() as session:
            record = session.run(
                query,
                organization_id=organization_id,
                project_id=project_id,
                relationship_id=relationship_id,
            ).single()
        if record is None:
            return None
        return _relationship_from_record(record)

    def delete_relationship(
        self,
        relationship_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> None:
        existing = self.get_relationship(relationship_id, organization_id, project_id)
        if existing is not None:
            self.save_relationship(
                replace(
                    existing,
                    is_deleted=True,
                    deleted_at=datetime.now(UTC),
                )
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
        relationship_filter = ""
        if relationship_type is not None:
            relationship_filter = f":{_safe_relationship_type(relationship_type)}"

        if normalized_direction == "outgoing":
            pattern = (
                "(entity:OntologyEntity "
                "{organization_id: $organization_id, project_id: $project_id, "
                "entity_type: $entity_type, entity_id: $entity_id})"
                f"-[r{relationship_filter}]->"
                "(other:OntologyEntity {organization_id: $organization_id, project_id: $project_id})"
            )
            source_alias = "entity"
            target_alias = "other"
        elif normalized_direction == "incoming":
            pattern = (
                "(other:OntologyEntity {organization_id: $organization_id, project_id: $project_id})-"
                f"[r{relationship_filter}]->"
                "(entity:OntologyEntity "
                "{organization_id: $organization_id, project_id: $project_id, "
                "entity_type: $entity_type, entity_id: $entity_id})"
            )
            source_alias = "other"
            target_alias = "entity"
        else:
            return sorted(
                [
                    *self.find_relationships(
                        entity_type,
                        entity_id,
                        direction="outgoing",
                        relationship_type=relationship_type,
                        organization_id=organization_id,
                        project_id=project_id,
                    ),
                    *self.find_relationships(
                        entity_type,
                        entity_id,
                        direction="incoming",
                        relationship_type=relationship_type,
                        organization_id=organization_id,
                        project_id=project_id,
                    ),
                ],
                key=lambda item: item.relationship_id,
            )

        query = f"""
        MATCH {pattern}
        WHERE coalesce({source_alias}.is_deleted, false) = false
          AND coalesce({target_alias}.is_deleted, false) = false
          AND coalesce(r.is_deleted, false) = false
        RETURN {source_alias} AS source,
               r,
               type(r) AS relationship_type,
               {target_alias} AS target
        ORDER BY r.relationship_id
        """
        with self._session() as session:
            records = list(
                session.run(
                    query,
                    organization_id=organization_id,
                    project_id=project_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
            )
        return [_relationship_from_record(record) for record in records]

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
        depth = int(depth)

        if direction == "outgoing":
            pattern = f"(entity)-[*1..{depth}]->(other:OntologyEntity)"
        elif direction == "incoming":
            pattern = f"(other:OntologyEntity)-[*1..{depth}]->(entity)"
        else:
            pattern = f"(entity)-[*1..{depth}]-(other:OntologyEntity)"

        query = f"""
        MATCH (entity:OntologyEntity {{
            organization_id: $organization_id,
            project_id: $project_id,
            entity_type: $entity_type,
            entity_id: $entity_id
        }})
        MATCH path = {pattern}
        WHERE other <> entity
          AND other.organization_id = $organization_id
          AND other.project_id = $project_id
          AND coalesce(entity.is_deleted, false) = false
          AND coalesce(other.is_deleted, false) = false
          AND all(r IN relationships(path) WHERE coalesce(r.is_deleted, false) = false)
        RETURN DISTINCT other
        ORDER BY other.entity_type, other.entity_id
        """
        with self._session() as session:
            records = list(
                session.run(
                    query,
                    organization_id=organization_id,
                    project_id=project_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
            )
        return [_entity_from_properties(dict(record["other"])) for record in records]

    def _session(self) -> Any:
        return self._driver.session(database=self._database)


class Neo4jOntologyGraphQueryRepository(OntologyGraphQueryRepository):
    """
    Read-only Neo4j adapter for ontology graph query APIs.
    """

    def __init__(
        self,
        graph_repository: Neo4jOntologyGraphRepository,
    ) -> None:
        self._graph_repository = graph_repository

    @classmethod
    def from_environment(cls) -> Neo4jOntologyGraphQueryRepository:
        return cls(Neo4jOntologyGraphRepository.from_environment())

    def close(self) -> None:
        self._graph_repository.close()

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

    def get_relationship(
        self,
        relationship_id: str,
    ) -> GraphRelationship | None:
        relationship = self._graph_repository.get_relationship(relationship_id)
        if relationship is None or relationship.is_deleted:
            return None
        source = self._graph_repository.get_entity(
            relationship.source_entity_type, relationship.source_entity_id
        )
        target = self._graph_repository.get_entity(
            relationship.target_entity_type, relationship.target_entity_id
        )
        if source is None or target is None or source.is_deleted or target.is_deleted:
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
        relationship_types: list[str] | None = None,
        entity_types: list[str] | None = None,
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
        relationship_types: list[str] | None = None,
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
        relationship_types: list[str] | None = None,
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
        relationship_types: list[str] | None = None,
        limit: int = DEFAULT_PATH_LIMIT,
    ) -> list[GraphPath]:
        query = f"""
        MATCH path = (source:OntologyEntity {{
            organization_id: $organization_id,
            project_id: $project_id,
            entity_type: $source_type,
            entity_id: $source_id
        }})-[*1..{int(max_depth)}]->(target:OntologyEntity {{
            organization_id: $organization_id,
            project_id: $project_id,
            entity_type: $target_type,
            entity_id: $target_id
        }})
        WHERE coalesce(source.is_deleted, false) = false
          AND coalesce(target.is_deleted, false) = false
          AND all(node IN nodes(path) WHERE coalesce(node.is_deleted, false) = false)
          AND all(r IN relationships(path) WHERE coalesce(r.is_deleted, false) = false)
          AND (size($relationship_types) = 0
           OR all(r IN relationships(path) WHERE type(r) IN $relationship_types)
          )
        RETURN path
        LIMIT $limit
        """
        with self._graph_repository._session() as session:
            records = list(
                session.run(
                    query,
                    organization_id="org_default",
                    project_id="project_default",
                    source_type=source_type,
                    source_id=source_id,
                    target_type=target_type,
                    target_id=target_id,
                    relationship_types=list(relationship_types or ()),
                    limit=limit,
                )
            )
        return [_path_from_neo4j_path(record["path"]) for record in records]

    def _subgraph(
        self,
        entity_type: str,
        entity_id: str,
        *,
        depth: int,
        direction: str,
        relationship_types: list[str] | None,
        entity_types: list[str] | None,
        limit: int,
    ) -> GraphSubgraph:
        pattern = _variable_length_pattern(direction, depth)
        query = f"""
        MATCH path = (source:OntologyEntity {{
            organization_id: $organization_id,
            project_id: $project_id,
            entity_type: $entity_type,
            entity_id: $entity_id
        }}){pattern}(node:OntologyEntity)
        WHERE coalesce(source.is_deleted, false) = false
          AND all(
              node_item IN nodes(path)
              WHERE node_item.organization_id = $organization_id
                AND node_item.project_id = $project_id
          )
          AND all(node_item IN nodes(path) WHERE coalesce(node_item.is_deleted, false) = false)
          AND all(r IN relationships(path) WHERE coalesce(r.is_deleted, false) = false)
          AND (size($relationship_types) = 0
           OR all(r IN relationships(path) WHERE type(r) IN $relationship_types)
          )
        WITH path
        WHERE size($entity_types) = 0
           OR all(n IN nodes(path)[1..] WHERE n.entity_type IN $entity_types)
        WITH collect(path)[0..$limit] AS paths
        UNWIND paths AS node_path
        UNWIND nodes(node_path) AS graph_node
        WITH paths, collect(DISTINCT graph_node) AS graph_nodes
        UNWIND paths AS rel_path
        UNWIND relationships(rel_path) AS graph_relationship
        RETURN paths,
               graph_nodes,
               collect(DISTINCT {{
                   source: startNode(graph_relationship),
                   relationship: graph_relationship,
                   relationship_type: type(graph_relationship),
                   target: endNode(graph_relationship)
               }}) AS graph_relationships
        """
        with self._graph_repository._session() as session:
            record = session.run(
                query,
                organization_id="org_default",
                project_id="project_default",
                entity_type=entity_type,
                entity_id=entity_id,
                relationship_types=list(relationship_types or ()),
                entity_types=list(entity_types or ()),
                limit=limit,
            ).single()
        if record is None:
            return GraphSubgraph()
        node_depths = _node_depths_from_paths(record["paths"])
        return GraphSubgraph(
            nodes=tuple(
                _graph_node_from_neo4j_node(node, node_depths)
                for node in record["graph_nodes"]
            ),
            edges=tuple(
                GraphEdge(_relationship_from_mapping(item))
                for item in record["graph_relationships"]
            ),
        )


def _safe_entity_label(value: str) -> str:
    try:
        return EntityType(value).value
    except ValueError as exc:
        raise OntologyRepositoryError(
            f"Unsafe or unknown ontology entity label: {value!r}."
        ) from exc


def _safe_relationship_type(value: str) -> str:
    try:
        return RelationshipType(value).value
    except ValueError as exc:
        raise OntologyRepositoryError(
            f"Unsafe or unknown ontology relationship type: {value!r}."
        ) from exc


def _variable_length_pattern(direction: str, depth: int) -> str:
    if direction == "outgoing":
        return f"-[*1..{int(depth)}]->"
    if direction == "incoming":
        return f"<-[*1..{int(depth)}]-"
    if direction == "both":
        return f"-[*1..{int(depth)}]-"
    raise OntologyRepositoryError(f"Unsupported query direction: {direction}.")


def _path_from_neo4j_path(path: Any) -> GraphPath:
    nodes = tuple(
        GraphNode(
            GraphEntity.from_ontology_entity(_entity_from_properties(dict(node))),
            depth=index,
        )
        for index, node in enumerate(path.nodes)
    )
    edges = []
    for index, relationship in enumerate(path.relationships):
        edges.append(
            GraphEdge(
                _relationship_from_path_parts(
                    path.nodes[index],
                    relationship,
                    path.nodes[index + 1],
                )
            )
        )
    return GraphPath(nodes=nodes, edges=tuple(edges))


def _node_depths_from_paths(paths: list[Any]) -> dict[tuple[str, str], int]:
    """Return the minimum hop depth for each entity in a Neo4j path result."""

    depths: dict[tuple[str, str], int] = {}
    for path in paths:
        for depth, node in enumerate(path.nodes):
            properties = dict(node)
            key = (str(properties["entity_type"]), str(properties["entity_id"]))
            existing = depths.get(key)
            if existing is None or depth < existing:
                depths[key] = depth
    return depths


def _graph_node_from_neo4j_node(
    node: Any,
    depths: dict[tuple[str, str], int],
) -> GraphNode:
    entity = GraphEntity.from_ontology_entity(
        _entity_from_properties(dict(node))
    )
    return GraphNode(
        entity,
        depth=depths.get((entity.entity_type, entity.entity_id), 0),
    )


def _relationship_from_path_parts(
    source: Any,
    relationship: Any,
    target: Any,
) -> GraphRelationship:
    source_properties = dict(source)
    target_properties = dict(target)
    relationship_properties = dict(relationship)
    return GraphRelationship(
        relationship_id=relationship_properties["relationship_id"],
        relationship_type=relationship.type,
        source_entity_id=source_properties["entity_id"],
        source_entity_type=source_properties["entity_type"],
        target_entity_id=target_properties["entity_id"],
        target_entity_type=target_properties["entity_type"],
        ontology_version=relationship_properties["ontology_version"],
        created_at=_datetime_from_string(relationship_properties["created_at"]),
        created_by=relationship_properties["created_by"],
        metadata=_json_load(relationship_properties.get("metadata_json")),
    )


def _relationship_from_mapping(value: Mapping[str, Any]) -> GraphRelationship:
    source_properties = dict(value["source"])
    target_properties = dict(value["target"])
    relationship_properties = dict(value["relationship"])
    return GraphRelationship(
        relationship_id=relationship_properties["relationship_id"],
        relationship_type=value["relationship_type"],
        source_entity_id=source_properties["entity_id"],
        source_entity_type=source_properties["entity_type"],
        target_entity_id=target_properties["entity_id"],
        target_entity_type=target_properties["entity_type"],
        ontology_version=relationship_properties["ontology_version"],
        created_at=_datetime_from_string(relationship_properties["created_at"]),
        created_by=relationship_properties["created_by"],
        metadata=_json_load(relationship_properties.get("metadata_json")),
    )


def _json_dump(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, default=str)


def _json_load(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    return dict(json.loads(value))


def _datetime_to_string(value: datetime) -> str:
    return value.isoformat()


def _datetime_from_string(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _entity_to_properties(entity: OntologyEntity) -> dict[str, Any]:
    return {
        "entity_id": entity.entity_id,
        "entity_type": entity.entity_type,
        "ontology_version": entity.ontology_version,
        "owner": entity.owner,
        "lifecycle": entity.lifecycle,
        "created_at": _datetime_to_string(entity.created_at),
        "immutable_attributes_json": _json_dump(entity.immutable_attributes),
        "mutable_attributes_json": _json_dump(entity.mutable_attributes),
        "metadata_json": _json_dump(entity.metadata),
        "organization_id": entity.organization_id,
        "project_id": entity.project_id,
        "is_deleted": entity.is_deleted,
        "deleted_at": (
            _datetime_to_string(entity.deleted_at) if entity.deleted_at else None
        ),
    }


def _entity_from_properties(properties: Mapping[str, Any]) -> OntologyEntity:
    return OntologyEntity(
        entity_id=properties["entity_id"],
        entity_type=properties["entity_type"],
        ontology_version=properties["ontology_version"],
        owner=properties["owner"],
        lifecycle=properties["lifecycle"],
        created_at=_datetime_from_string(properties["created_at"]),
        immutable_attributes=_json_load(properties.get("immutable_attributes_json")),
        mutable_attributes=_json_load(properties.get("mutable_attributes_json")),
        metadata=_json_load(properties.get("metadata_json")),
        organization_id=properties.get("organization_id", "org_default"),
        project_id=properties.get("project_id", "project_default"),
        is_deleted=bool(properties.get("is_deleted", False)),
        deleted_at=(
            _datetime_from_string(properties["deleted_at"])
            if properties.get("deleted_at")
            else None
        ),
    )


def _relationship_to_properties(
    relationship: OntologyRelationship,
) -> dict[str, Any]:
    return {
        "relationship_id": relationship.relationship_id,
        "relationship_type": relationship.relationship_type,
        "ontology_version": relationship.ontology_version,
        "created_at": _datetime_to_string(relationship.created_at),
        "created_by": relationship.created_by,
        "metadata_json": _json_dump(relationship.metadata),
        "organization_id": relationship.organization_id,
        "project_id": relationship.project_id,
        "is_deleted": relationship.is_deleted,
        "deleted_at": (
            _datetime_to_string(relationship.deleted_at)
            if relationship.deleted_at
            else None
        ),
    }


def _relationship_from_record(record: Any) -> OntologyRelationship:
    source = dict(record["source"])
    target = dict(record["target"])
    relationship = dict(record["r"])
    return OntologyRelationship(
        relationship_id=relationship["relationship_id"],
        relationship_type=record["relationship_type"],
        source_entity_id=source["entity_id"],
        source_entity_type=source["entity_type"],
        target_entity_id=target["entity_id"],
        target_entity_type=target["entity_type"],
        ontology_version=relationship["ontology_version"],
        created_at=_datetime_from_string(relationship["created_at"]),
        created_by=relationship["created_by"],
        metadata=_json_load(relationship.get("metadata_json")),
        organization_id=relationship.get(
            "organization_id", source.get("organization_id", "org_default")
        ),
        project_id=relationship.get(
            "project_id", source.get("project_id", "project_default")
        ),
        is_deleted=bool(relationship.get("is_deleted", False)),
        deleted_at=(
            _datetime_from_string(relationship["deleted_at"])
            if relationship.get("deleted_at")
            else None
        ),
    )
