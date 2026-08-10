from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import get_mcp_audit_log
from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.mcp.dto import WriteEnvelope


def _client(
    audit_log: MCPExecutionAuditLog,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_mcp_audit_log] = lambda: audit_log
    return TestClient(app)


def test_lists_mcp_audit_records_with_filters() -> None:
    audit_log = MCPExecutionAuditLog.in_memory()
    _started_record(audit_log, request_id="request-1", actor_id="agent-1")
    _started_record(audit_log, request_id="request-2", actor_id="agent-2")
    client = _client(audit_log)

    response = client.get(
        "/api/v1/mcp/audit",
        params={"actor_id": "agent-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["records"]) == 1
    assert payload["records"][0]["request_id"] == "request-1"
    assert payload["records"][0]["request_summary"]["provider_config"] == (
        "<redacted>"
    )


def test_get_mcp_audit_record_marks_stale_started_as_interrupted() -> None:
    audit_log = MCPExecutionAuditLog.in_memory()
    record = _started_record(audit_log)
    audit_log._store.save(  # type: ignore[attr-defined]
        replace(
            record,
            started_at=datetime.now(UTC) - timedelta(seconds=120),
        )
    )
    client = _client(audit_log)

    response = client.get(
        f"/api/v1/mcp/audit/{record.audit_id}",
        params={"interrupted_after_seconds": 60},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "STARTED"
    assert payload["interrupted"] is True
    assert payload["interrupted_reason"] is not None


def test_finds_mcp_audit_by_request_and_correlation() -> None:
    audit_log = MCPExecutionAuditLog.in_memory()
    _started_record(
        audit_log,
        request_id="request-1",
        correlation_id="corr-1",
    )
    client = _client(audit_log)

    by_request = client.get("/api/v1/mcp/audit/by-request/request-1")
    by_correlation = client.get("/api/v1/mcp/audit/by-correlation/corr-1")

    assert by_request.status_code == 200
    assert by_request.json()["records"][0]["request_id"] == "request-1"
    assert by_correlation.status_code == 200
    assert by_correlation.json()["records"][0]["correlation_id"] == "corr-1"


def test_get_mcp_audit_record_returns_404_for_missing_record() -> None:
    client = _client(MCPExecutionAuditLog.in_memory())

    response = client.get("/api/v1/mcp/audit/missing")

    assert response.status_code == 404


def _started_record(
    audit_log: MCPExecutionAuditLog,
    *,
    request_id: str = "request-1",
    correlation_id: str | None = None,
    actor_id: str = "agent-1",
):
    envelope = WriteEnvelope(
        request_id=request_id,
        correlation_id=correlation_id,
        idempotency_key=f"idem-{request_id}",
        requested_by=actor_id,
        actor_type="AGENT",
        reason="governance audit lookup",
    )
    return audit_log.start(
        tool_name="evaluation.submit_async",
        operation_type="SUBMIT_EVALUATION_JOB",
        resource_type="evaluation",
        resource_id="execution-1",
        envelope=envelope,
        payload={
            "execution_id": "execution-1",
            "provider_config": {"api_key": "secret"},
        },
    )
