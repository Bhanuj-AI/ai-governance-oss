from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from fastapi.testclient import TestClient

from kavach.api.app import create_app
from kavach.api.dependencies import get_ontology_graph_query_service
from kavach.mcp.clients import RestClient
from kavach.mcp.server import create_server
from kavach.ontology import (
    EntityType,
    InMemoryOntologyGraphQueryRepository,
    InMemoryOntologyGraphRepository,
    OntologyEntity,
    OntologyGraphQueryService,
    OntologyRelationship,
    RelationshipType,
)


def main() -> None:
    service = _query_service()
    app = create_app()
    app.dependency_overrides[get_ontology_graph_query_service] = (
        lambda: service
    )
    client = TestClient(app)

    entity = client.get("/api/v1/ontology/entities/Candidate/candidate-1")
    relationships = client.get(
        "/api/v1/ontology/entities/Candidate/candidate-1/relationships",
        params={"direction": "outgoing", "limit": 1},
    )
    downstream = client.get(
        "/api/v1/ontology/entities/Candidate/candidate-1/downstream",
        params={"depth": 2},
    )
    paths = client.get(
        "/api/v1/ontology/path",
        params={
            "source_type": "Candidate",
            "source_id": "candidate-1",
            "target_type": "Actor",
            "target_id": "owner",
            "relationship_type": ["USES", "CREATED_BY"],
            "max_depth": 2,
        },
    )

    print("Graph entity lookup:")
    print(f"  entity_type={entity.json()['entity_type']}")
    print(f"  entity_id={entity.json()['entity_id']}")
    print("Relationship page:")
    print(f"  first_relationship={relationships.json()['items'][0]['relationship_id']}")
    print(f"  next_cursor={relationships.json()['next_cursor']}")
    print("Downstream traversal:")
    print(f"  nodes={len(downstream.json()['nodes'])}")
    print(f"  edges={len(downstream.json()['edges'])}")
    print("Path query:")
    print(f"  paths={len(paths.json()['paths'])}")

    def transport(
        method: str,
        path: str,
        query: Mapping[str, Any] | None,
        body: Mapping[str, Any] | None,
    ) -> Any:
        response = client.request(method, path, params=query)
        return response.json()

    mcp_server = create_server(
        rest_client=RestClient(
            base_url="http://testserver",
            transport=transport,
        )
    )
    mcp_result = mcp_server.call_tool(
        "ontology_graph.downstream",
        {
            "entity_type": "Candidate",
            "entity_id": "candidate-1",
            "depth": 2,
        },
    )
    print("MCP graph tool:")
    print(f"  status={mcp_result.status}")


def _query_service() -> OntologyGraphQueryService:
    repository = InMemoryOntologyGraphRepository()
    for entity in (
        _entity(EntityType.CANDIDATE.value, "candidate-1"),
        _entity(EntityType.PROMPT_VERSION.value, "prompt-v1"),
        _entity(EntityType.ACTOR.value, "owner"),
    ):
        repository.save_entity(entity)
    for relationship in (
        _relationship(
            "rel-1",
            RelationshipType.USES.value,
            EntityType.CANDIDATE.value,
            "candidate-1",
            EntityType.PROMPT_VERSION.value,
            "prompt-v1",
        ),
        _relationship(
            "rel-2",
            RelationshipType.CREATED_BY.value,
            EntityType.PROMPT_VERSION.value,
            "prompt-v1",
            EntityType.ACTOR.value,
            "owner",
        ),
        _relationship(
            "rel-3",
            RelationshipType.OWNED_BY.value,
            EntityType.CANDIDATE.value,
            "candidate-1",
            EntityType.ACTOR.value,
            "owner",
        ),
    ):
        repository.save_relationship(relationship)
    return OntologyGraphQueryService(
        InMemoryOntologyGraphQueryRepository(repository)
    )


def _entity(entity_type: str, entity_id: str) -> OntologyEntity:
    return OntologyEntity(
        entity_id=entity_id,
        entity_type=entity_type,
        owner="owner",
        lifecycle="ACTIVE",
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


def _relationship(
    relationship_id: str,
    relationship_type: str,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
) -> OntologyRelationship:
    return OntologyRelationship(
        relationship_id=relationship_id,
        relationship_type=relationship_type,
        source_entity_type=source_type,
        source_entity_id=source_id,
        target_entity_type=target_type,
        target_entity_id=target_id,
        created_by="owner",
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


if __name__ == "__main__":
    main()
