from __future__ import annotations

from kavach.mcp.clients import RestClient
from kavach.mcp.dto import (
    OntologyGraphEntityRequest,
    OntologyGraphNeighbourhoodRequest,
    OntologyGraphPathRequest,
    OntologyGraphRelationshipRequest,
    OntologyGraphRelationshipsRequest,
    OntologyGraphTraversalRequest,
)
from kavach.mcp.handlers._rest_tool import rest_get
from kavach.mcp.observability import MCPMetrics
from kavach.mcp.registry import ToolRegistry


def register_ontology_graph_tools(
    registry: ToolRegistry,
    rest_client: RestClient,
    metrics: MCPMetrics,
) -> None:
    registry.register(
        name="ontology_graph.get_entity",
        description="Return one ontology graph entity by type and ID.",
        request_model=OntologyGraphEntityRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/ontology/entities/{request.entity_type}/{request.entity_id}",
        ),
    )
    registry.register(
        name="ontology_graph.get_relationships",
        description="Return relationships connected to an ontology entity.",
        request_model=OntologyGraphRelationshipsRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/ontology/entities/{request.entity_type}/{request.entity_id}/relationships",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="ontology_graph.get_relationship",
        description="Return one ontology graph relationship by ID.",
        request_model=OntologyGraphRelationshipRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/ontology/relationships/{request.relationship_id}",
        ),
    )
    registry.register(
        name="ontology_graph.neighbourhood",
        description="Return a bounded ontology neighbourhood.",
        request_model=OntologyGraphNeighbourhoodRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/ontology/entities/{request.entity_type}/{request.entity_id}/neighbourhood",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="ontology_graph.upstream",
        description="Return bounded upstream ontology lineage.",
        request_model=OntologyGraphTraversalRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/ontology/entities/{request.entity_type}/{request.entity_id}/upstream",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="ontology_graph.downstream",
        description="Return bounded downstream ontology impact.",
        request_model=OntologyGraphTraversalRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/ontology/entities/{request.entity_type}/{request.entity_id}/downstream",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="ontology_graph.find_paths",
        description="Return bounded directed paths between ontology entities.",
        request_model=OntologyGraphPathRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            "/api/v1/ontology/path",
            query=request.to_query_params(),
        ),
    )
