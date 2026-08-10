from __future__ import annotations

from typing import Any

from ai_governance.mcp.clients import RestClient, RestClientError
from ai_governance.mcp.mappers import MCPResponseMapper
from ai_governance.mcp.observability import MCPMetrics


def rest_get(
    rest_client: RestClient,
    metrics: MCPMetrics,
    path: str,
    *,
    query: dict[str, Any] | None = None,
) -> Any:
    metrics.record_rest_call()
    try:
        return MCPResponseMapper.from_rest_payload(rest_client.get(path, query=query))
    except RestClientError:
        metrics.record_rest_failure()
        raise


def rest_post(
    rest_client: RestClient,
    metrics: MCPMetrics,
    path: str,
    *,
    body: dict[str, Any],
) -> Any:
    metrics.record_rest_call()
    try:
        return MCPResponseMapper.from_rest_payload(rest_client.post(path, body=body))
    except RestClientError:
        metrics.record_rest_failure()
        raise
