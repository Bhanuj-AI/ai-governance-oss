from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi.testclient import TestClient

from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.mcp.authentication import InboundRequestAuthenticationContext
from ai_governance.mcp.clients import RestClient
from ai_governance.mcp.runtime_context import (
    McpRuntimeContext,
    reset_runtime_context,
    set_runtime_context,
)
from ai_governance.mcp.server import create_server, get_mcp_settings
from ai_governance.mcp.transports.streamable_http import create_mcp_http_app
from ai_governance.tenancy.domain import ActorType, AuthenticatedPrincipal


def test_streamable_http_settings_defaults(monkeypatch) -> None:
    for name in (
        "AI_GOVERNANCE_MCP_TRANSPORT",
        "AI_GOVERNANCE_MCP_HTTP_HOST",
        "AI_GOVERNANCE_MCP_HTTP_PORT",
        "AI_GOVERNANCE_MCP_HTTP_PATH",
        "AI_GOVERNANCE_MCP_PUBLIC_URL",
        "AI_GOVERNANCE_MCP_HTTP_STATELESS",
        "AI_GOVERNANCE_MCP_HTTP_JSON_RESPONSE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = get_mcp_settings()

    assert settings.transport == "stdio"
    assert settings.http_host == "127.0.0.1"
    assert settings.http_port == 8002
    assert settings.http_path == "/mcp"
    assert settings.protected_resource_url == "http://localhost:8002/mcp"
    assert settings.http_stateless is True
    assert settings.http_json_response is True


def test_streamable_http_rejects_invalid_transport_configuration(monkeypatch) -> None:
    monkeypatch.setenv("AI_GOVERNANCE_MCP_TRANSPORT", "both")

    try:
        get_mcp_settings()
    except ValueError as exc:
        assert "AI_GOVERNANCE_MCP_TRANSPORT" in str(exc)
    else:  # pragma: no cover - makes the configuration guarantee explicit.
        raise AssertionError("invalid MCP transport configuration was accepted")


def test_streamable_http_uses_canonical_tools_and_health(monkeypatch) -> None:
    monkeypatch.setenv("AI_GOVERNANCE_AUTH_MODE", "development")
    monkeypatch.setenv("AI_GOVERNANCE_MCP_HTTP_ALLOWED_HOSTS", "testserver")
    client = RestClient("http://control-plane", transport=lambda *_: {"ok": True})
    server = create_server(client, audit_log=MCPExecutionAuditLog.in_memory())
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    with TestClient(create_mcp_http_app(server=server)) as http:
        assert http.get("/health").json() == {"status": "ok"}
        initialized = http.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"},
                },
            },
        )
        tools = http.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        call = http.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "provider_list", "arguments": {}},
            },
        )

    assert initialized.status_code == 200
    assert tools.json()["result"]["tools"][0]["name"] == "authorization_permissions"
    assert all(
        tool["name"].replace("_", "").replace("-", "").isalnum()
        for tool in tools.json()["result"]["tools"]
    )
    result = call.json()["result"]
    assert result["structuredContent"]["status"] == "ok"
    assert result["isError"] is False


def test_streamable_http_requires_bearer_token_in_keycloak_mode(monkeypatch) -> None:
    monkeypatch.setenv("AI_GOVERNANCE_AUTH_MODE", "keycloak")
    monkeypatch.setenv(
        "AI_GOVERNANCE_OIDC_ISSUER", "http://keycloak.localhost:8080/realms/ai-governance"
    )
    monkeypatch.setenv("AI_GOVERNANCE_MCP_HTTP_ALLOWED_HOSTS", "testserver")

    with TestClient(create_mcp_http_app()) as http:
        response = http.post(
            "/mcp",
            headers={"Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_authorization"
    assert response.headers["www-authenticate"] == (
        'Bearer resource_metadata="http://localhost:8002/'
        '.well-known/oauth-protected-resource/mcp"'
    )


def test_streamable_http_exposes_protected_resource_metadata(monkeypatch) -> None:
    monkeypatch.setenv("AI_GOVERNANCE_AUTH_MODE", "keycloak")
    monkeypatch.setenv("AI_GOVERNANCE_MCP_HTTP_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv(
        "AI_GOVERNANCE_OIDC_ISSUER", "http://keycloak.localhost:8080/realms/ai-governance"
    )

    with TestClient(create_mcp_http_app()) as http:
        response = http.get("/.well-known/oauth-protected-resource/mcp")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "resource": "http://localhost:8002/mcp",
        "authorization_servers": [
            "http://keycloak.localhost:8080/realms/ai-governance"
        ],
        "scopes_supported": ["openid", "profile", "email"],
        "bearer_methods_supported": ["header"],
        "resource_name": "AI Governance Control Plane MCP",
    }


def test_streamable_http_allows_configured_browser_preflight(monkeypatch) -> None:
    monkeypatch.setenv("AI_GOVERNANCE_AUTH_MODE", "keycloak")
    monkeypatch.setenv("AI_GOVERNANCE_MCP_HTTP_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("AI_GOVERNANCE_MCP_HTTP_ALLOWED_ORIGINS", "http://localhost:6274")

    with TestClient(create_mcp_http_app()) as http:
        response = http.options(
            "/mcp",
            headers={
                "Origin": "http://localhost:6274",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "authorization,content-type,mcp-protocol-version"
                ),
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:6274"
    assert "mcp-protocol-version" in response.headers[
        "access-control-allow-headers"
    ].lower()


def test_streamable_http_forwards_authenticated_tenant_request_context(monkeypatch) -> None:
    import ai_governance.mcp.clients.rest_client as rest_client_module
    import ai_governance.mcp.transports.streamable_http as http_transport

    monkeypatch.setenv("AI_GOVERNANCE_AUTH_MODE", "keycloak")
    monkeypatch.setenv("AI_GOVERNANCE_MCP_HTTP_ALLOWED_HOSTS", "testserver")
    observed: list[dict[str, str]] = []

    class Response:
        def read(self) -> bytes:
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *_: Any) -> None:
            return None

    class AuthenticationService:
        def validate(self, token: str) -> AuthenticatedPrincipal:
            assert token == "caller-token"
            return AuthenticatedPrincipal(
                subject="user-a",
                principal_type=ActorType.USER,
                organization_id=None,
                client_id="client-a",
                issuer="https://issuer.example",
            )

    def fake_urlopen(request, timeout):
        del timeout
        observed.append(dict(request.headers.items()))
        return Response()

    monkeypatch.setattr(rest_client_module, "urlopen", fake_urlopen)
    def authentication_service_for(audience: str) -> AuthenticationService:
        assert audience == "http://localhost:8002/mcp"
        return AuthenticationService()

    monkeypatch.setattr(
        http_transport,
        "get_authentication_service",
        authentication_service_for,
    )
    server = create_server(
        RestClient("http://control-plane"), audit_log=MCPExecutionAuditLog.in_memory()
    )
    headers = {
        "Authorization": "Bearer caller-token",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "X-Request-Id": "request-a",
        "X-Correlation-Id": "correlation-a",
    }
    with TestClient(create_mcp_http_app(server=server)) as http:
        response = http.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "context_current",
                    "arguments": {
                        "context": {
                            "organization_id": "org-a",
                            "project_id": "project-a",
                        }
                    },
                },
            },
        )

    assert response.status_code == 200
    assert len(observed) == 1
    assert {
        "Authorization": observed[0]["Authorization"],
        "X-ai-governance-organization-id": observed[0]["X-ai-governance-organization-id"],
        "X-ai-governance-project-id": observed[0]["X-ai-governance-project-id"],
        "X-request-id": observed[0]["X-request-id"],
        "X-correlation-id": observed[0]["X-correlation-id"],
    } == {
        "Authorization": "Bearer caller-token",
        "X-ai-governance-organization-id": "org-a",
        "X-ai-governance-project-id": "project-a",
        "X-request-id": "request-a",
        "X-correlation-id": "correlation-a",
    }


def test_request_scoped_bearer_context_isolated_across_concurrent_calls(
    monkeypatch,
) -> None:
    import ai_governance.mcp.clients.rest_client as rest_client_module

    observed: list[dict[str, str]] = []

    class Response:
        def read(self) -> bytes:
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *_: Any) -> None:
            return None

    def fake_urlopen(request, timeout):
        del timeout
        observed.append(dict(request.headers.items()))
        return Response()

    monkeypatch.setattr(rest_client_module, "urlopen", fake_urlopen)
    client = RestClient("http://control-plane")

    def invoke(token: str, organization_id: str) -> None:
        runtime_token = set_runtime_context(
            McpRuntimeContext(
                authentication=InboundRequestAuthenticationContext(f"Bearer {token}"),
                request_id=f"request-{organization_id}",
            )
        )
        try:
            client.with_tenant_context(organization_id).get("/api/v1/providers")
        finally:
            reset_runtime_context(runtime_token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda item: invoke(*item), (("token-user-a", "org-a"), ("token-user-b", "org-b"))))

    assert {headers["Authorization"] for headers in observed} == {
        "Bearer token-user-a",
        "Bearer token-user-b",
    }
    assert {headers["X-ai-governance-organization-id"] for headers in observed} == {
        "org-a",
        "org-b",
    }
