from __future__ import annotations

from kavach.mcp.clients import RestClient
from kavach.mcp.dto import (
    MCPAuditFindByCorrelationRequest,
    MCPAuditFindByRequestRequest,
    MCPAuditGetRequest,
    MCPAuditListRequest,
)
from kavach.mcp.handlers._rest_tool import rest_get
from kavach.mcp.observability import MCPMetrics
from kavach.mcp.registry import ToolRegistry


def register_mcp_audit_tools(
    registry: ToolRegistry,
    rest_client: RestClient,
    metrics: MCPMetrics,
) -> None:
    registry.register(
        name="mcp_audit.list",
        description="List MCP execution audit records with optional filters.",
        request_model=MCPAuditListRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            "/api/v1/mcp/audit",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="mcp_audit.get",
        description="Return one MCP execution audit record by audit ID.",
        request_model=MCPAuditGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/mcp/audit/{request.audit_id}",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="mcp_audit.find_by_request",
        description="Find MCP execution audit records by request ID.",
        request_model=MCPAuditFindByRequestRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/mcp/audit/by-request/{request.request_id}",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="mcp_audit.find_by_correlation",
        description="Find MCP execution audit records by correlation ID.",
        request_model=MCPAuditFindByCorrelationRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/mcp/audit/by-correlation/{request.correlation_id}",
            query=request.to_query_params(),
        ),
    )
