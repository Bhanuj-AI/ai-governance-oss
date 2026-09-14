"""REST coverage for provider-neutral WORKFLOW_STEP execution evidence."""

from __future__ import annotations

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.routers.agent_execution import (
    get_agent_execution_service,
    router,
)
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
    InMemoryAgentExecutionRepository,
)
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.tenancy.domain import TenantContext


def _context_from_headers(
    x_ai_governance_organization_id: str = Header(...),
    x_ai_governance_project_id: str = Header(...),
) -> TenantContext:
    return TenantContext(
        x_ai_governance_organization_id,
        x_ai_governance_project_id,
        "runtime-client",
        "request-id",
    )


def _client() -> TestClient:
    app = FastAPI()
    service = AgentExecutionService(
        InMemoryAgentExecutionRepository(),
        InMemoryAgentExecutionEventRepository(),
    )
    app.include_router(router)
    app.dependency_overrides[get_agent_execution_service] = lambda: service
    app.dependency_overrides[get_compatible_tenant_context] = _context_from_headers
    return TestClient(app)


def _headers(
    organization_id: str = "org-a", project_id: str = "project-a"
) -> dict[str, str]:
    return {
        "X-AI-Governance-Organization-Id": organization_id,
        "X-AI-Governance-Project-Id": project_id,
    }


def _start_execution(client: TestClient) -> str:
    response = client.post(
        "/api/v1/agent-executions",
        headers=_headers(),
        json={
            "agent_id": "claims-agent",
            "agent_name": "Claims Agent",
            "agent_version": "1.0",
            "external_execution_id": "langgraph-run-1",
            "runtime_provider": "langgraph",
        },
    )
    assert response.status_code == 201
    return response.json()["execution"]["execution_id"]


def test_ingests_and_round_trips_workflow_step_evidence() -> None:
    client = _client()
    execution_id = _start_execution(client)
    started = client.post(
        f"/api/v1/agent-executions/{execution_id}/events",
        headers=_headers(),
        json={
            "event_type": "WORKFLOW_STEP",
            "step_id": "step-check-policy",
            "step_name": "check_policy",
            "lifecycle": "STARTED",
            "source_kind": "langgraph.node",
            "idempotency_key": "workflow-step-start",
            "attributes": {"duration_ms": 2},
        },
    )

    assert started.status_code == 201
    payload = started.json()["event"]
    assert payload["event_type"] == "WORKFLOW_STEP"
    assert payload["step_id"] == "step-check-policy"
    assert payload["step_name"] == "check_policy"
    assert payload["lifecycle"] == "STARTED"
    assert payload["source_kind"] == "langgraph.node"
    assert payload["sequence_number"] == 1

    completed = client.post(
        f"/api/v1/agent-executions/{execution_id}/events",
        headers=_headers(),
        json={
            "event_type": "WORKFLOW_STEP",
            "step_id": "step-check-policy",
            "step_name": "check_policy",
            "lifecycle": "COMPLETED",
            "source_kind": "langgraph.node",
            "idempotency_key": "workflow-step-complete",
        },
    )
    assert completed.status_code == 201
    assert completed.json()["event"]["sequence_number"] == 2

    detail = client.get(
        f"/api/v1/agent-executions/{execution_id}", headers=_headers()
    )
    assert detail.status_code == 200
    events = detail.json()["events"]
    assert [event["sequence_number"] for event in events] == [0, 1, 2]
    assert detail.json()["event_counts"] == {
        "EXECUTION_STARTED": 1,
        "WORKFLOW_STEP": 2,
    }
    assert events[2]["step_id"] == "step-check-policy"
    assert events[2]["lifecycle"] == "COMPLETED"


def test_workflow_step_rejects_missing_required_fields() -> None:
    client = _client()
    execution_id = _start_execution(client)

    response = client.post(
        f"/api/v1/agent-executions/{execution_id}/events",
        headers=_headers(),
        json={"event_type": "WORKFLOW_STEP", "step_id": "step-1"},
    )

    assert response.status_code == 422
    assert "step_name" in response.text
    assert "lifecycle" in response.text


def test_workflow_step_isolation_and_tool_call_compatibility() -> None:
    client = _client()
    execution_id = _start_execution(client)

    tool_call = client.post(
        f"/api/v1/agent-executions/{execution_id}/events",
        headers=_headers(),
        json={
            "event_type": "TOOL_CALL",
            "actor_id": "policy-api",
            "actor_type": "TOOL",
            "attributes": {"tool": "policy-api"},
        },
    )
    assert tool_call.status_code == 201
    assert tool_call.json()["event"]["event_type"] == "TOOL_CALL"
    assert tool_call.json()["event"]["step_id"] is None

    foreign_organization = client.post(
        f"/api/v1/agent-executions/{execution_id}/events",
        headers=_headers("org-b", "project-a"),
        json={
            "event_type": "WORKFLOW_STEP",
            "step_id": "step-1",
            "step_name": "check_policy",
            "lifecycle": "STARTED",
        },
    )
    foreign_project = client.get(
        f"/api/v1/agent-executions/{execution_id}",
        headers=_headers("org-a", "project-b"),
    )

    assert foreign_organization.status_code == 404
    assert foreign_project.status_code == 404
