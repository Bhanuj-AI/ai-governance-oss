from __future__ import annotations

from ai_governance.mcp.clients import RestClient
from ai_governance.mcp.dto import JobListRequest, JobStatusRequest
from ai_governance.mcp.handlers._rest_tool import rest_get
from ai_governance.mcp.observability import MCPMetrics
from ai_governance.mcp.registry import ToolRegistry


def register_job_tools(
    registry: ToolRegistry,
    rest_client: RestClient,
    metrics: MCPMetrics,
) -> None:
    registry.register(
        name="job.list",
        description="List jobs with optional status and type filters.",
        request_model=JobListRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            "/api/v1/jobs",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="job.status",
        description="Return job status and metadata by ID.",
        request_model=JobStatusRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/jobs/{request.job_id}",
        ),
    )
