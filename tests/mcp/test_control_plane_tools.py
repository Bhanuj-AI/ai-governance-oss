from __future__ import annotations

from typing import Any

from ai_governance.mcp.clients import RestClient
from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.mcp.server import create_server


def test_control_plane_tool_requires_explicit_context():
    server = create_server(
        RestClient("http://ai-governance", transport=lambda *args: {}),
        audit_log=MCPExecutionAuditLog.in_memory(),
    )
    result = server.call_tool("project.list", {})
    assert result.status == "error"


def test_project_list_forwards_tenant_scoped_path():
    calls: list[tuple[Any, ...]] = []

    def transport(*args):
        calls.append(args)
        return []

    server = create_server(RestClient("http://ai-governance", transport=transport))
    result = server.call_tool(
        "project.list",
        {"context": {"organization_id": "org_a", "project_id": "project_a"}},
    )
    assert result.status == "ok"
    assert calls[0][1] == "/api/v1/organizations/org_a/projects"


def test_controlled_tenant_write_supports_dry_run_and_audit():
    server = create_server(
        RestClient("http://ai-governance", transport=lambda *args: {}),
        audit_log=MCPExecutionAuditLog.in_memory(),
    )
    result = server.call_tool(
        "project.create",
        {
            "context": {"organization_id": "org_a", "project_id": "project_a"},
            "request_id": "request-1",
            "idempotency_key": "key-1",
            "reason": "Create isolated project",
            "dry_run": True,
            "project_id": "project_new",
            "name": "New",
            "slug": "new",
        },
    )
    assert result.status == "ok"
    assert result.data["status"] == "VALIDATED"
    record = server.audit_log.all_records()[0]
    assert (record.organization_id, record.project_id, record.status) == (
        "org_a",
        "project_a",
        "DRY_RUN",
    )
