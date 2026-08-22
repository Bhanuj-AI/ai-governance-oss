from __future__ import annotations

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import (
    get_governance_decision_repository,
    get_job_repository,
    get_ontology_sync_event_repository,
)
from ai_governance.ontology.synchronization import (
    OntologySyncEvent,
    OntologySyncEventStatus,
)
from ai_governance.repositories import (
    InMemoryGovernanceDecisionRepository,
    InMemoryJobRepository,
    InMemoryOntologySyncEventRepository,
)


def _client() -> tuple[TestClient, InMemoryOntologySyncEventRepository]:
    decision_repository = InMemoryGovernanceDecisionRepository()
    job_repository = InMemoryJobRepository()
    sync_event_repository = InMemoryOntologySyncEventRepository()
    app = create_app()
    app.dependency_overrides[get_governance_decision_repository] = (
        lambda: decision_repository
    )
    app.dependency_overrides[get_job_repository] = lambda: job_repository
    app.dependency_overrides[get_ontology_sync_event_repository] = (
        lambda: sync_event_repository
    )
    return TestClient(app), sync_event_repository


def test_dashboard_summary_returns_home_read_model() -> None:
    client, _sync_event_repository = _client()
    decision = client.post(
        "/api/v1/decisions/evaluate",
        json={
            "target_type": "Candidate",
            "target_id": "candidate-1",
            "decision_type": "APPROVE",
            "policy_ids": [],
            "correlation_id": "dashboard-corr",
            "request_id": "dashboard-req",
            "metadata": {"source": "dashboard-test"},
        },
    )
    job = client.post(
        "/api/v1/jobs",
        json={
            "job_type": "EVALUATION",
            "input_refs": {"evaluation_id": "eval-1"},
            "idempotency_key": "dashboard-job",
            "submitted_by": "tester",
        },
    )

    response = client.get("/api/v1/dashboard")

    assert decision.status_code == 200
    assert job.status_code == 201
    assert response.status_code == 200
    payload = response.json()
    assert payload["governance_statistics"][0] == {
        "label": "Governance Decisions",
        "value": 1,
        "description": "Persisted governance outcomes",
    }
    assert payload["governance_statistics"][2]["value"] == 1
    assert payload["ontology_projection_statistics"] == [
        {
            "label": "Graph Nodes",
            "value": 0,
            "description": "Live ontology entities in the graph store.",
        },
        {
            "label": "Graph Relationships",
            "value": 0,
            "description": "Live ontology edges in the graph store.",
        },
        {
            "label": "Sync Queue",
            "value": 0,
            "description": "Ontology events awaiting projection.",
        },
        {
            "label": "Dead-Letter Events",
            "value": 0,
            "description": "Events requiring operator review.",
        },
    ]
    assert payload["platform_statistics"][0]["label"] == "Decisions Today"
    assert payload["platform_statistics"][0]["value"] == 1
    assert payload["platform_statistics"][2] == {
        "label": "Running Jobs",
        "value": 0,
        "description": None,
    }
    assert [item["component"] for item in payload["platform_health"]] == [
        "REST API",
        "MCP Server",
        "Database",
        "Neo4j Graph Store",
        "Ontology Synchronizer",
        "Job Workers",
    ]
    assert payload["recent_activity"]
    assert {
        "Candidate/candidate-1",
        f"Job/{job.json()['job_id']}",
    }.issubset({item["resource"] for item in payload["recent_activity"]})
    assert all(
        not item["resource"].startswith("GovernanceDecision/")
        for item in payload["recent_activity"]
    )


def test_dashboard_hides_governance_decision_projection_events() -> None:
    client, sync_event_repository = _client()
    sync_event_repository.save(
        OntologySyncEvent(
            event_type="GovernanceDecisionCreated",
            entity_type="GovernanceDecision",
            entity_id="decision-1",
            correlation_id="dashboard-corr",
        )
    )

    response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    assert response.json()["recent_activity"] == []


def test_dashboard_reports_dead_letters_as_a_sync_warning() -> None:
    client, sync_event_repository = _client()
    sync_event_repository.save(
        OntologySyncEvent(
            event_type="GovernanceDecisionCreated",
            entity_type="GovernanceDecision",
            entity_id="decision-1",
            correlation_id="dashboard-corr",
            status=OntologySyncEventStatus.DEAD_LETTER,
            retry_count=4,
        )
    )

    response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    synchronizer = next(
        component
        for component in response.json()["platform_health"]
        if component["component"] == "Ontology Synchronizer"
    )
    assert synchronizer == {
        "component": "Ontology Synchronizer",
        "status": "Warning",
        "detail": "1 event requires review or retry.",
    }


def test_dashboard_resource_is_in_openapi() -> None:
    client, _sync_event_repository = _client()

    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/dashboard" in paths
