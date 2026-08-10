from __future__ import annotations

from ai_governance.mcp.clients import RestClient
from ai_governance.mcp.dto import (
    EmptyRequest,
    ExperimentCandidatesRequest,
    ExperimentComparisonRequest,
    ExperimentGetRequest,
    ExperimentLeaderboardRequest,
    ExperimentRunsRequest,
)
from ai_governance.mcp.handlers._rest_tool import rest_get
from ai_governance.mcp.observability import MCPMetrics
from ai_governance.mcp.registry import ToolRegistry


def register_experiment_tools(
    registry: ToolRegistry,
    rest_client: RestClient,
    metrics: MCPMetrics,
) -> None:
    registry.register(
        name="experiment.list",
        description="Return experiments visible through the REST control plane.",
        request_model=EmptyRequest,
        handler=lambda _request: rest_get(
            rest_client,
            metrics,
            "/api/v1/experiments",
        ),
    )
    registry.register(
        name="experiment.get",
        description="Return one experiment by ID.",
        request_model=ExperimentGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/experiments/{request.experiment_id}",
        ),
    )
    registry.register(
        name="experiment.candidates",
        description="Return candidates registered for an experiment.",
        request_model=ExperimentCandidatesRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/experiments/{request.experiment_id}/candidates",
        ),
    )
    registry.register(
        name="experiment.runs",
        description="Return evaluation runs for an experiment.",
        request_model=ExperimentRunsRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/experiments/{request.experiment_id}/runs",
        ),
    )
    registry.register(
        name="experiment.compare_candidates",
        description=(
            "Compare two experiment candidates by configuration and latest "
            "completed evaluation metrics."
        ),
        request_model=ExperimentComparisonRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/experiments/{request.experiment_id}/comparison",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="experiment.leaderboard",
        description="Return the latest leaderboard for an experiment.",
        request_model=ExperimentLeaderboardRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/experiments/{request.experiment_id}/leaderboard",
        ),
    )
