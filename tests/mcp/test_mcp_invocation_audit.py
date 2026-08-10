from __future__ import annotations

from ai_governance.mcp.invocation_audit import MCPInvocationAuditLog


def test_sqlite_invocation_audit_records_redacted_terminal_evidence(tmp_path) -> None:
    audit_log = MCPInvocationAuditLog.sqlite(tmp_path / "mcp-audit.db")
    received = audit_log.received(
        invocation_id="invocation-1",
        request_id="request-1",
        correlation_id="correlation-1",
        tool_name="model.get",
        organization_id="org-1",
        project_id="project-1",
        actor_id="user-1",
        actor_type="USER",
        client_id="copilot",
        authorization_decision="ALLOWED",
        payload={"context": {"organization_id": "org-1"}, "token": "secret"},
    )

    audit_log.complete(
        received,
        status="SUCCEEDED",
        authorization_decision="ALLOWED",
        response={"sensitive": "output is hashed, not persisted"},
    )

    [record] = audit_log.all_records()
    assert record.status == "SUCCEEDED"
    assert record.argument_summary["token"] == "<redacted>"
    assert record.response_classification == "object"
    assert record.response_hash is not None
    assert "sensitive" not in record.argument_summary


def test_same_invocation_id_upserts_retry_evidence() -> None:
    audit_log = MCPInvocationAuditLog.in_memory()
    received = audit_log.received(
        invocation_id="stable-request-id",
        request_id="stable-request-id",
        correlation_id="correlation-1",
        tool_name="model.get",
        organization_id="org-1",
        project_id=None,
        actor_id="user-1",
        actor_type="USER",
        client_id="copilot",
        authorization_decision="ALLOWED",
        payload={},
    )
    audit_log.complete(
        received,
        status="FAILED",
        authorization_decision="ALLOWED",
        error_category="UPSTREAM_UNAVAILABLE",
    )
    retry = audit_log.received(
        invocation_id="stable-request-id",
        request_id="stable-request-id",
        correlation_id="correlation-1",
        tool_name="model.get",
        organization_id="org-1",
        project_id=None,
        actor_id="user-1",
        actor_type="USER",
        client_id="copilot",
        authorization_decision="ALLOWED",
        payload={},
    )
    audit_log.complete(
        retry, status="SUCCEEDED", authorization_decision="ALLOWED", response={}
    )

    [record] = audit_log.all_records()
    assert record.status == "SUCCEEDED"
