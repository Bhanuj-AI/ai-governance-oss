from __future__ import annotations

from kavach.mcp.clients import RestClient
from kavach.mcp.dto import ReplayGetRequest, ReplayListRequest, ReplayResultRequest
from kavach.mcp.handlers._rest_tool import rest_get
from kavach.mcp.observability import MCPMetrics
from kavach.mcp.registry import ToolRegistry


def register_replay_tools(
    registry: ToolRegistry,
    rest_client: RestClient,
    metrics: MCPMetrics,
) -> None:
    registry.register(
        name="replay.get",
        description="Return one tenant-scoped replay request.",
        request_model=ReplayGetRequest,
        handler=lambda request: rest_get(
            rest_client, metrics, f"/api/v1/replays/{request.replay_id}"
        ),
    )
    registry.register(
        name="replay.result",
        description="Return immutable governed evidence for a completed replay.",
        request_model=ReplayResultRequest,
        handler=lambda request: rest_get(
            rest_client, metrics, f"/api/v1/replays/{request.replay_id}/result"
        ),
    )
    registry.register(
        name="replay.list",
        description="List replay requests visible in the active tenant project.",
        request_model=ReplayListRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            "/api/v1/replays",
            query=request.to_query_params(),
        ),
    )
