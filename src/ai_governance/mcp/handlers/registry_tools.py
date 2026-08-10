from __future__ import annotations

from ai_governance.mcp.clients import RestClient
from ai_governance.mcp.dto import (
    DatasetGetRequest,
    EmptyRequest,
    ModelGetRequest,
    PromptGetRequest,
)
from ai_governance.mcp.handlers._rest_tool import rest_get
from ai_governance.mcp.observability import MCPMetrics
from ai_governance.mcp.registry import ToolRegistry


def register_registry_tools(
    registry: ToolRegistry,
    rest_client: RestClient,
    metrics: MCPMetrics,
) -> None:
    registry.register(
        name="registry.list_prompts",
        description="Return visible prompt registry entries.",
        request_model=EmptyRequest,
        handler=lambda _request: rest_get(
            rest_client,
            metrics,
            "/api/v1/prompts",
        ),
    )
    registry.register(
        name="registry.get_prompt",
        description="Return visible versions for one logical prompt name.",
        request_model=PromptGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/prompts/{request.prompt_name}",
        ),
    )
    registry.register(
        name="registry.list_models",
        description="Return model registry entries.",
        request_model=EmptyRequest,
        handler=lambda _request: rest_get(
            rest_client,
            metrics,
            "/api/v1/models",
        ),
    )
    registry.register(
        name="registry.get_model",
        description="Return one model registry entry by ID.",
        request_model=ModelGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/models/{request.model_id}",
        ),
    )
    registry.register(
        name="registry.list_datasets",
        description="Return dataset registry entries.",
        request_model=EmptyRequest,
        handler=lambda _request: rest_get(
            rest_client,
            metrics,
            "/api/v1/datasets",
        ),
    )
    registry.register(
        name="registry.get_dataset",
        description="Return one dataset registry entry by ID.",
        request_model=DatasetGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/datasets/{request.dataset_id}",
        ),
    )
