from __future__ import annotations

from kavach.mcp.clients import RestClient
from kavach.mcp.dto import EmptyRequest
from kavach.mcp.handlers._rest_tool import rest_get
from kavach.mcp.observability import MCPMetrics
from kavach.mcp.registry import ToolRegistry


def register_provider_tools(
    registry: ToolRegistry,
    rest_client: RestClient,
    metrics: MCPMetrics,
) -> None:
    registry.register(
        name="provider.list",
        description="Return registered evaluation providers.",
        request_model=EmptyRequest,
        handler=lambda _request: rest_get(
            rest_client,
            metrics,
            "/api/v1/providers",
        ),
    )
