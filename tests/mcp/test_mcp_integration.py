from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from kavach.api.app import create_app
from kavach.mcp.audit import MCPExecutionAuditLog
from kavach.mcp.clients import RestClient, RestClientError
from kavach.mcp.server import create_server


def _test_client_transport(client: TestClient):
    def transport(
        method: str,
        path: str,
        query: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> Any:
        response = client.request(
            method,
            path,
            params=query,
            json=body,
        )
        if response.status_code >= 400:
            raise RestClientError(
                status_code=response.status_code,
                payload=response.json(),
            )
        return response.json()

    return transport


def test_mcp_tool_invokes_rest_api_provider_discovery() -> None:
    client = TestClient(create_app())
    server = create_server(
        RestClient(
            base_url="http://testserver",
            transport=_test_client_transport(client),
        ),
        audit_log=MCPExecutionAuditLog.in_memory(),
    )

    result = server.call_tool("provider.list")

    assert result.status == "ok"
    assert result.data[0]["name"] == "mock"
    assert result.data[0]["capabilities"]["supported_metrics"]


def test_mcp_tool_invokes_rest_api_experiment_list() -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/api/v1/experiments",
        json={
            "name": "claim-validation",
            "description": "Compare claim validation candidates",
            "metadata": {"owner": "mcp-test"},
        },
    )
    assert create_response.status_code == 201

    server = create_server(
        RestClient(
            base_url="http://testserver",
            transport=_test_client_transport(client),
        ),
        audit_log=MCPExecutionAuditLog.in_memory(),
    )

    result = server.call_tool("experiment.list")

    assert result.status == "ok"
    assert result.data[0]["name"] == "claim-validation"
    assert result.data[0]["owner"] == "mcp-test"
