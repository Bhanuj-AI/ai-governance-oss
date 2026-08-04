from __future__ import annotations

from kavach.mcp.clients import RestClient
from kavach.mcp.dto import (
    EvaluationGetRequest,
    EvaluationHistoryRequest,
    EvaluationLatestRequest,
)
from kavach.mcp.handlers._rest_tool import rest_get
from kavach.mcp.observability import MCPMetrics
from kavach.mcp.registry import ToolRegistry


def register_evaluation_tools(
    registry: ToolRegistry,
    rest_client: RestClient,
    metrics: MCPMetrics,
) -> None:
    registry.register(
        name="evaluation.history",
        description="Return persisted evaluations for an execution.",
        request_model=EvaluationHistoryRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/evaluations/history/{request.execution_id}",
        ),
    )
    registry.register(
        name="evaluation.latest",
        description="Return the latest persisted evaluation for an execution.",
        request_model=EvaluationLatestRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/evaluations/latest/{request.execution_id}",
        ),
    )
    registry.register(
        name="evaluation.metrics",
        description="Return a persisted evaluation result and its metrics by ID.",
        request_model=EvaluationGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/evaluations/{request.evaluation_id}",
        ),
    )
    registry.register(
        name="evaluation.get",
        description="Return a persisted evaluation result and its metrics by ID.",
        request_model=EvaluationGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/evaluations/{request.evaluation_id}",
        ),
    )
