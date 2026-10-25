"""HTTP integration coverage for runtime action execution receipt ingestion."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.routers.agent_execution import (
    get_agent_execution_service,
    router,
)
from ai_governance.domain.agent_execution import (
    ActorType,
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
)
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
    InMemoryAgentExecutionRepository,
)
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.tenancy.domain import TenantContext

NOW = datetime(2026, 10, 25, 8, 0, tzinfo=UTC)
ARGUMENT_DIGEST = "sha256:" + "a" * 64
RESULT_DIGEST = "sha256:" + "b" * 64
FINGERPRINT = "c" * 64


def _context_from_headers(
    x_ai_governance_organization_id: str = Header(...),
    x_ai_governance_project_id: str = Header(...),
    x_ai_governance_runtime_actor_id: str = Header("runtime-a"),
) -> TenantContext:
    return TenantContext(
        x_ai_governance_organization_id,
        x_ai_governance_project_id,
        x_ai_governance_runtime_actor_id,
        "request-a",
    )


def _client() -> TestClient:
    executions = InMemoryAgentExecutionRepository()
    events = InMemoryAgentExecutionEventRepository()
    executions.save(
        AgentExecution(
            execution_id="execution-1",
            organization_id="org-a",
            project_id="project-a",
            agent_id="claims-agent",
            agent_name="Claims Agent",
            agent_version="1",
            external_execution_id="runtime-execution-1",
            runtime_provider="external-runtime",
            status=AgentExecutionStatus.RUNNING,
            started_at=NOW,
            completed_at=None,
            correlation_id="correlation-1",
            parent_execution_id=None,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    events.save(
        AgentExecutionEvent(
            event_id="decision-1",
            execution_id="execution-1",
            organization_id="org-a",
            project_id="project-a",
            event_type=EventType.RUNTIME_ACTION_AUTHORIZATION,
            sequence_number=1,
            occurred_at=NOW,
            received_at=NOW,
            correlation_id="correlation-1",
            causation_id=None,
            actor_id="runtime-a",
            actor_type=ActorType.GOVERNANCE,
            attributes={
                "authorization_outcome": "ALLOW",
                "request_fingerprint": FINGERPRINT,
                "action_id": "claims.update",
                "actor_id": "runtime-a",
                "tool_arguments_digest": ARGUMENT_DIGEST,
            },
        )
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent_execution_service] = lambda: AgentExecutionService(
        executions, events, clock=lambda: NOW
    )
    app.dependency_overrides[get_compatible_tenant_context] = _context_from_headers
    return TestClient(app)


def _headers(
    organization_id: str = "org-a",
    runtime_actor_id: str = "runtime-a",
) -> dict[str, str]:
    return {
        "X-AI-Governance-Organization-Id": organization_id,
        "X-AI-Governance-Project-Id": "project-a",
        "X-AI-Governance-Runtime-Actor-Id": runtime_actor_id,
    }


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision_id": "decision-1",
        "request_fingerprint": FINGERPRINT,
        "action_id": "claims.update",
        "runtime_tool_call_id": "runtime-call-1",
        "tool_arguments_digest": ARGUMENT_DIGEST,
        "status": "SUCCEEDED",
        "reason_code": "RUNTIME_REPORTED_SUCCESS",
        "idempotency_key": "delivery-1",
        "result_reference": "artifact://claims/42/result",
        "result_digest": RESULT_DIGEST,
    }
    payload.update(overrides)
    return payload


def test_receipt_endpoint_persists_typed_attestation_and_deduplicates() -> None:
    client = _client()

    response = client.post(
        "/api/v1/agent-executions/execution-1/runtime-action-receipts",
        headers=_headers(),
        json=_payload(),
    )
    duplicate = client.post(
        "/api/v1/agent-executions/execution-1/runtime-action-receipts",
        headers=_headers(),
        json=_payload(idempotency_key="delivery-retry"),
    )

    assert response.status_code == 201
    assert duplicate.status_code == 201
    receipt = response.json()["event"]["runtime_action_execution_receipt"]
    assert receipt["schema_version"] == "runtime-action-execution-receipt/v1"
    assert receipt["status"] == "SUCCEEDED"
    assert receipt["attested_by"] == "runtime-a"
    assert duplicate.json()["event"]["event_id"] == response.json()["event"]["event_id"]


def test_receipt_endpoint_rejects_conflict_and_cross_tenant_runtime_forgery() -> None:
    client = _client()
    path = "/api/v1/agent-executions/execution-1/runtime-action-receipts"

    assert client.post(path, headers=_headers(), json=_payload()).status_code == 201
    conflicting = client.post(
        path,
        headers=_headers(),
        json=_payload(
            status="FAILED",
            reason_code="RUNTIME_REPORTED_FAILURE",
            result_reference=None,
            result_digest=None,
        ),
    )
    forged = client.post(path, headers=_headers("org-b"), json=_payload())
    other_runtime = client.post(
        path,
        headers=_headers(runtime_actor_id="runtime-b"),
        json=_payload(idempotency_key="runtime-b-delivery"),
    )
    forged_identity = client.post(
        path,
        headers=_headers(),
        json=_payload(attested_by="runtime-forged"),
    )

    assert conflicting.status_code == 409
    assert forged.status_code == 404
    assert other_runtime.status_code == 422
    assert forged_identity.status_code == 422
