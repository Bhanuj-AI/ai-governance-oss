from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from kavach.ontology import (
    GraphEdge,
    GraphEntity,
    GraphNode,
    GraphPath,
    GraphQueryPage,
    GraphRelationship,
    GraphSubgraph,
)


class GraphEntityResponse(BaseModel):
    entity_id: str
    entity_type: str
    lifecycle: str
    owner: str
    ontology_version: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    immutable_attributes: dict[str, Any] = Field(default_factory=dict)
    mutable_attributes: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, entity: GraphEntity) -> GraphEntityResponse:
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


class GraphRelationshipResponse(BaseModel):
    relationship_id: str
    relationship_type: str
    source_entity_id: str
    source_entity_type: str
    target_entity_id: str
    target_entity_type: str
    ontology_version: str
    created_at: datetime
    created_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(
        cls,
        relationship: GraphRelationship,
    ) -> GraphRelationshipResponse:
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


class GraphNodeResponse(BaseModel):
    entity: GraphEntityResponse
    depth: int

    @classmethod
    def from_domain(cls, node: GraphNode) -> GraphNodeResponse:
        return cls(
            entity=GraphEntityResponse.from_domain(node.entity),
            depth=node.depth,
        )


class GraphEdgeResponse(BaseModel):
    relationship: GraphRelationshipResponse

    @classmethod
    def from_domain(cls, edge: GraphEdge) -> GraphEdgeResponse:
        return cls(
            relationship=GraphRelationshipResponse.from_domain(edge.relationship)
        )


class GraphSubgraphResponse(BaseModel):
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]

    @classmethod
    def from_domain(cls, subgraph: GraphSubgraph) -> GraphSubgraphResponse:
        return cls(
            nodes=[GraphNodeResponse.from_domain(node) for node in subgraph.nodes],
            edges=[GraphEdgeResponse.from_domain(edge) for edge in subgraph.edges],
        )


class GraphPathResponse(BaseModel):
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]

    @classmethod
    def from_domain(cls, path: GraphPath) -> GraphPathResponse:
        return cls(
            nodes=[GraphNodeResponse.from_domain(node) for node in path.nodes],
            edges=[GraphEdgeResponse.from_domain(edge) for edge in path.edges],
        )


class GraphRelationshipPageResponse(BaseModel):
    items: list[GraphRelationshipResponse]
    limit: int
    next_cursor: str | None = None

    @classmethod
    def from_domain(
        cls,
        page: GraphQueryPage[GraphRelationship],
    ) -> GraphRelationshipPageResponse:
        return cls(
            items=[GraphRelationshipResponse.from_domain(item) for item in page.items],
            limit=page.limit,
            next_cursor=page.next_cursor,
        )


class GraphPathListResponse(BaseModel):
    paths: list[GraphPathResponse]

    @classmethod
    def from_domain(
        cls,
        paths: list[GraphPath],
    ) -> GraphPathListResponse:
        return cls(paths=[GraphPathResponse.from_domain(path) for path in paths])
