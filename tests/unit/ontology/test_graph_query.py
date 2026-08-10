from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

import pytest
from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import (
    get_governance_decision_repository,
    get_job_repository,
    get_mcp_audit_log,
    get_ontology_graph_query_service,
    get_ontology_graph_repository,
    get_policy_administration_repository,
)
from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.domain.prompts import PromptStatus
from ai_governance.mcp.clients import RestClient
from ai_governance.mcp.server import create_server
from ai_governance.ontology import (
    EntityType,
    InMemoryOntologyGraphQueryRepository,
    InMemoryOntologyGraphRepository,
    OntologyEntity,
    OntologyGraphQueryService,
    OntologyRelationship,
    RelationshipType,
)
from ai_governance.ontology.neo4j_repository import _node_depths_from_paths
from ai_governance.repositories.in_memory import InMemoryGovernanceDecisionRepository
from ai_governance.repositories.in_memory import InMemoryJobRepository
from ai_governance.repositories.in_memory_policy_administration_repository import (
    InMemoryPolicyAdministrationRepository,
)


def test_graph_query_service_reads_relationships_subgraphs_and_paths() -> None:
    service = _query_service()

    page = service.find_relationships(
        EntityType.CANDIDATE.value,
        "candidate-1",
        direction="outgoing",
        limit=1,
    )
    next_page = service.find_relationships(
        EntityType.CANDIDATE.value,
        "candidate-1",
        direction="outgoing",
        limit=1,
        cursor=page.next_cursor,
    )
    downstream = service.get_downstream_impact(
        EntityType.CANDIDATE.value,
        "candidate-1",
        depth=2,
    )
    upstream = service.get_upstream_lineage(
        EntityType.ACTOR.value,
        "owner",
        depth=2,
    )
    paths = service.find_paths(
        EntityType.CANDIDATE.value,
        "candidate-1",
        EntityType.ACTOR.value,
        "owner",
        max_depth=2,
        relationship_types=(
            RelationshipType.USES.value,
            RelationshipType.CREATED_BY.value,
        ),
    )

    assert [item.relationship_id for item in page.items] == ["rel-1"]
    assert page.next_cursor == "1"
    assert [item.relationship_id for item in next_page.items] == ["rel-3"]
    assert next_page.next_cursor is None
    assert [node.entity.entity_id for node in downstream.nodes] == [
        "candidate-1",
        "owner",
        "prompt-v1",
    ]
    assert {node.entity.entity_id for node in upstream.nodes} == {
        "candidate-1",
        "owner",
        "prompt-v1",
    }
    assert len(paths) == 1
    assert [node.entity.entity_id for node in paths[0].nodes] == [
        "candidate-1",
        "prompt-v1",
        "owner",
    ]


def test_neo4j_neighbourhood_depths_use_the_shortest_returned_path() -> None:
    class FakePath:
        def __init__(self, nodes: list[dict[str, str]]) -> None:
            self.nodes = nodes

    depths = _node_depths_from_paths(
        [
            FakePath(
                [
                    {"entity_type": "PromptVersion", "entity_id": "prompt-v2"},
                    {"entity_type": "Candidate", "entity_id": "candidate-1"},
                    {"entity_type": "Experiment", "entity_id": "experiment-1"},
                ]
            ),
            FakePath(
                [
                    {"entity_type": "PromptVersion", "entity_id": "prompt-v2"},
                    {"entity_type": "Experiment", "entity_id": "experiment-1"},
                ]
            ),
        ]
    )

    assert depths == {
        ("PromptVersion", "prompt-v2"): 0,
        ("Candidate", "candidate-1"): 1,
        ("Experiment", "experiment-1"): 1,
    }


def test_graph_query_service_validates_bounds_and_types() -> None:
    service = _query_service()

    with pytest.raises(ValueError, match="Unknown ontology entity type"):
        service.get_entity("UnknownType", "id")
    with pytest.raises(ValueError, match="depth must be between"):
        service.get_downstream_impact(
            EntityType.CANDIDATE.value,
            "candidate-1",
            depth=6,
        )
    with pytest.raises(ValueError, match="limit must be between"):
        service.find_relationships(
            EntityType.CANDIDATE.value,
            "candidate-1",
            limit=501,
        )


def test_graph_query_hides_tombstoned_entities_and_relationships() -> None:
    repository = InMemoryOntologyGraphRepository()
    source = OntologyEntity(
        entity_id="candidate-deleted",
        entity_type=EntityType.CANDIDATE,
        owner="owner",
        lifecycle="CREATED",
    )
    target = OntologyEntity(
        entity_id="prompt-deleted",
        entity_type=EntityType.PROMPT_VERSION,
        owner="owner",
        lifecycle="ACTIVE",
    )
    relationship = OntologyRelationship(
        relationship_id="deleted-edge",
        relationship_type=RelationshipType.USES,
        source_entity_id=source.entity_id,
        source_entity_type=source.entity_type,
        target_entity_id=target.entity_id,
        target_entity_type=target.entity_type,
        created_by="owner",
    )
    repository.save_entity(source)
    repository.save_entity(target)
    repository.save_relationship(relationship)
    query = OntologyGraphQueryService(InMemoryOntologyGraphQueryRepository(repository))

    repository.delete_relationship(relationship.relationship_id)

    assert repository.get_relationship(relationship.relationship_id) is not None
    assert query.find_relationships(source.entity_type, source.entity_id).items == ()

    repository.delete_entity(target.entity_type, target.entity_id)

    assert repository.get_entity(target.entity_type, target.entity_id) is not None
    assert query.get_entity(target.entity_type, target.entity_id) is None
    subgraph = query.get_downstream_impact(source.entity_type, source.entity_id)
    assert [node.entity.entity_id for node in subgraph.nodes] == [source.entity_id]
    assert subgraph.edges == ()


def test_graph_query_rest_endpoints_return_stable_dtos() -> None:
    app = create_app()
    app.dependency_overrides[get_ontology_graph_query_service] = _query_service
    client = TestClient(app)

    entity_response = client.get(
        "/api/v1/ontology/entities/Candidate/candidate-1"
    )
    relationships_response = client.get(
        "/api/v1/ontology/entities/Candidate/candidate-1/relationships",
        params={"direction": "outgoing", "limit": 1},
    )
    neighbourhood_response = client.get(
        "/api/v1/ontology/entities/Candidate/candidate-1/neighbourhood",
        params={"depth": 1, "relationship_type": "USES"},
    )
    path_response = client.get(
        "/api/v1/ontology/path",
        params={
            "source_type": "Candidate",
            "source_id": "candidate-1",
            "target_type": "Actor",
            "target_id": "owner",
            "max_depth": 2,
            "relationship_type": [
                RelationshipType.USES.value,
                RelationshipType.CREATED_BY.value,
            ],
        },
    )

    assert entity_response.status_code == 200
    assert entity_response.json()["entity_type"] == "Candidate"
    assert relationships_response.status_code == 200
    assert relationships_response.json()["items"][0]["relationship_id"] == "rel-1"
    assert neighbourhood_response.status_code == 200
    assert {
        node["entity"]["entity_id"]
        for node in neighbourhood_response.json()["nodes"]
    } == {"candidate-1", "prompt-v1"}
    assert path_response.status_code == 200
    assert path_response.json()["paths"][0]["edges"][0]["relationship"][
        "relationship_type"
    ] == "USES"


def test_demo_seed_endpoint_populates_in_memory_graph() -> None:
    repository = InMemoryOntologyGraphRepository()
    decision_repository = InMemoryGovernanceDecisionRepository()
    job_repository = InMemoryJobRepository()
    audit_log = MCPExecutionAuditLog.in_memory()
    policy_repository = InMemoryPolicyAdministrationRepository()

    def query_service() -> OntologyGraphQueryService:
        return OntologyGraphQueryService(
            InMemoryOntologyGraphQueryRepository(repository)
        )

    app = create_app()
    app.dependency_overrides[get_ontology_graph_repository] = lambda: repository
    app.dependency_overrides[get_ontology_graph_query_service] = query_service
    app.dependency_overrides[get_governance_decision_repository] = (
        lambda: decision_repository
    )
    app.dependency_overrides[get_policy_administration_repository] = (
        lambda: policy_repository
    )
    app.dependency_overrides[get_job_repository] = lambda: job_repository
    app.dependency_overrides[get_mcp_audit_log] = lambda: audit_log
    client = TestClient(app)

    first_response = client.post("/api/v1/ontology/demo/seed")
    second_response = client.post("/api/v1/ontology/demo/seed")
    neighbourhood_response = client.get(
        "/api/v1/ontology/entities/Candidate/candidate-1/neighbourhood",
        params={"depth": 2},
    )
    decisions_response = client.get("/api/v1/decisions")
    policies_response = client.get("/api/v1/policies")
    jobs_response = client.get("/api/v1/jobs")
    audit_response = client.get("/api/v1/audit")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert neighbourhood_response.status_code == 200
    assert {
        node["entity"]["entity_id"]
        for node in neighbourhood_response.json()["nodes"]
    } >= {
        "candidate-1",
        "prompt-v1",
        "model-v1",
        "dataset-v1",
        "eval-run-approve",
        "eval-result-approve",
        "policy-release-gate",
    }
    assert decisions_response.status_code == 200
    decisions = decisions_response.json()["decisions"]
    assert len(decisions) == 4
    assert {decision["status"] for decision in decisions} == {
        "APPROVED",
        "BLOCKED",
        "PROPOSED",
        "REJECTED",
    }
    assert policies_response.status_code == 200
    policies = policies_response.json()
    assert policies[0]["policy_id"] == "policy-release-gate"
    assert policies[0]["status"] == "ACTIVE"
    assert jobs_response.status_code == 200
    jobs = jobs_response.json()["jobs"]
    assert len(jobs) == 10
    assert {job["job_type"] for job in jobs} == {
        "DRIFT_ANALYSIS",
        "EVALUATION",
        "EXPERIMENT",
        "REPLAY",
    }
    assert {job["status"] for job in jobs} == {
        "CANCELLED",
        "FAILED",
        "SUCCEEDED",
    }
    assert audit_response.status_code == 200
    assert audit_response.json()["total"] == 8

    decision_id = next(
        decision["decision_id"]
        for decision in decisions
        if decision["status"] == "APPROVED"
    )
    detail_response = client.get(f"/api/v1/decisions/{decision_id}/detail")
    lineage_response = client.get(f"/api/v1/decisions/{decision_id}/lineage")

    assert detail_response.status_code == 200
    assert detail_response.json()["policy_outcomes"][0]["effect"] == "APPROVE"
    assert lineage_response.status_code == 200
    assert {
        node["entity"]["entity_id"]
        for node in lineage_response.json()["subgraph"]["nodes"]
    } >= {decision_id, "candidate-1", "owner"}

    effects = {}
    for decision in decisions:
        response = client.get(
            f"/api/v1/decisions/{decision['decision_id']}/detail"
        )
        effects[decision["target"]["target_id"]] = response.json()[
            "policy_outcomes"
        ][0]["effect"]

    assert effects == {
        "candidate-1": "APPROVE",
        "candidate-2": "INVESTIGATE",
        "candidate-3": "REJECT",
        "candidate-4": "BLOCK",
    }


def test_ontology_graph_mcp_tools_call_rest_paths() -> None:
    calls: list[tuple[str, str, Mapping[str, Any] | None]] = []

    def transport(
        method: str,
        path: str,
        query: Mapping[str, Any] | None,
        body: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        calls.append((method, path, query))
        return {"ok": True, "path": path, "query": dict(query or {})}

    server = create_server(
        rest_client=RestClient(
            base_url="http://api",
            transport=transport,
        )
    )

    tool_names = {tool.name for tool in server.list_tools()}
    result = server.call_tool(
        "ontology_graph.downstream",
        {
            "entity_type": "Candidate",
            "entity_id": "candidate-1",
            "depth": 2,
            "relationship_type": ["USES"],
        },
    )

    assert "ontology_graph.get_entity" in tool_names
    assert "ontology_graph.find_paths" in tool_names
    assert result.status == "ok"
    assert calls[-1] == (
        "GET",
        "/api/v1/ontology/entities/Candidate/candidate-1/downstream",
        {"depth": 2, "relationship_type": ["USES"], "limit": 100},
    )


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
        lifecycle=PromptStatus.ACTIVE.value,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        immutable_attributes={},
        mutable_attributes={},
        metadata={},
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
