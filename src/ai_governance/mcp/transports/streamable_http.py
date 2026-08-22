"""Dual-era Streamable HTTP transport over the canonical tool registry.

The official MCP SDK performs protocol negotiation at this boundary: legacy
handshake/session requests and 2026-07-28 self-contained requests converge on
the same registered tools.  Nothing below this adapter is protocol-era aware.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolResult, TextContent
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ai_governance.api.dependencies.authentication import get_authentication_service
from ai_governance.mcp.authentication import (
    DevelopmentAuthenticationContext,
    InboundRequestAuthenticationContext,
)
from ai_governance.mcp.runtime_context import (
    McpRuntimeContext,
    reset_runtime_context,
    set_runtime_context,
)
from ai_governance.mcp.server import (
    AIGovernanceMCPServer,
    MCPSettings,
    create_server,
    get_mcp_settings,
)
from ai_governance.tenancy.authentication import AuthenticationError
from ai_governance.tenancy.domain import AuthenticatedPrincipal
from ai_governance.version import __version__


class _AIGovernanceMCPServerAdapter(MCPServer):
    """SDK protocol implementation backed by the existing canonical registry."""

    def __init__(
        self,
        ai_governance_server: AIGovernanceMCPServer,
        canonical_tool_names: dict[str, str],
        **kwargs: Any,
    ) -> None:
        self._ai_governance_server = ai_governance_server
        self._canonical_tool_names = canonical_tool_names
        super().__init__(**kwargs)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Any = None,
    ) -> CallToolResult:
        del context
        result = self._ai_governance_server.call_tool(
            self._canonical_tool_names.get(name, name), arguments
        )
        payload = result.model_dump(mode="json")
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(payload))],
            structuredContent=payload,
            isError=result.status == "error",
        )


class _McpRequestAuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Any,
        *,
        auth_mode: str,
        protected_resource_url: str,
        canonical_server: AIGovernanceMCPServer,
    ) -> None:
        super().__init__(app)
        self._auth_mode = auth_mode
        self._protected_resource_url = protected_resource_url
        self._canonical_server = canonical_server

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in {
            "/health",
            "/ready",
            _protected_resource_metadata_path_from_url(self._protected_resource_url),
        }:
            return await call_next(request)

        # The SDK owns wire validation and version negotiation. We only record
        # anonymous adoption telemetry here so the legacy path can be retired
        # from evidence rather than assumption. Modern requests must identify
        # their version in this header; every other request is legacy-era.
        protocol_version = request.headers.get("mcp-protocol-version")
        protocol_era = (
            "2026-07-28"
            if protocol_version == "2026-07-28"
            else "legacy"
        )
        self._canonical_server.metrics.record_protocol_era(protocol_era)

        principal: AuthenticatedPrincipal | None = None
        authorization = request.headers.get("authorization")
        actor_id = request.headers.get("x-ai-governance-actor-id")
        if self._auth_mode == "keycloak":
            if actor_id:
                return _authentication_error(
                    "development_actor_header_forbidden",
                    "X-AI-Governance-Actor-Id is not accepted in keycloak mode.",
                    status_code=400,
                    protected_resource_url=self._protected_resource_url,
                )
            token = _extract_bearer_token(authorization)
            if token is None:
                return _authentication_error(
                    "missing_authorization"
                    if authorization is None
                    else "invalid_authorization",
                    "Authorization header is required."
                    if authorization is None
                    else "Authorization must use the Bearer scheme.",
                    protected_resource_url=self._protected_resource_url,
                )
            try:
                principal = get_authentication_service(
                    self._protected_resource_url
                ).validate(token)
            except AuthenticationError as exc:
                return _authentication_error(
                    exc.code,
                    str(exc),
                    protected_resource_url=self._protected_resource_url,
                )
            authentication = InboundRequestAuthenticationContext(authorization or "")
        else:
            authentication = DevelopmentAuthenticationContext()

        context = McpRuntimeContext(
            authentication=authentication,
            principal=principal,
            request_id=request.headers.get("x-request-id") or str(uuid4()),
            correlation_id=request.headers.get("x-correlation-id"),
            development_actor_id=actor_id,
            inbound_headers={
                key: value
                for key, value in request.headers.items()
                if key
                in {
                    "authorization",
                    "x-ai-governance-organization-id",
                    "x-ai-governance-project-id",
                    "x-request-id",
                    "x-correlation-id",
                }
            },
        )
        token = set_runtime_context(context)
        try:
            return await call_next(request)
        finally:
            reset_runtime_context(token)


def create_mcp_http_app(
    *,
    server: AIGovernanceMCPServer | None = None,
    settings: MCPSettings | None = None,
) -> Any:
    """Build the stateless Streamable HTTP ASGI app at the configured path."""
    settings = settings or get_mcp_settings()
    canonical_server = server or create_server()
    canonical_server.metrics.transport = "streamable-http"
    canonical_tool_names: dict[str, str] = {}
    for description in canonical_server.list_tools():
        mcp_name = _mcp_tool_name(description.name)
        existing_name = canonical_tool_names.setdefault(mcp_name, description.name)
        if existing_name != description.name:
            raise ValueError(
                "MCP tool names collide after protocol normalization: "
                f"{existing_name!r} and {description.name!r}."
            )

    mcp = _AIGovernanceMCPServerAdapter(
        canonical_server,
        canonical_tool_names=canonical_tool_names,
        name="ai-governance",
        version=__version__,
    )
    for description in canonical_server.list_tools():
        _register_tool_schema(
            mcp,
            _mcp_tool_name(description.name),
            description.description,
            description.input_schema,
        )

    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @mcp.custom_route("/ready", methods=["GET"], include_in_schema=False)
    async def ready(_: Request) -> JSONResponse:
        # The canonical registry and configuration have already been constructed.
        return JSONResponse({"status": "ready"})

    metadata_path = _protected_resource_metadata_path(settings.http_path)

    @mcp.custom_route(metadata_path, methods=["GET"], include_in_schema=False)
    async def protected_resource_metadata(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "resource": settings.protected_resource_url,
                "authorization_servers": [_oidc_issuer()],
                "scopes_supported": ["openid", "profile", "email"],
                "bearer_methods_supported": ["header"],
                "resource_name": "AI Governance Control Plane MCP",
            }
        )

    app = mcp.streamable_http_app(
        streamable_http_path=settings.http_path,
        stateless_http=settings.http_stateless,
        json_response=settings.http_json_response,
        host=settings.http_host,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=_host_patterns(settings.http_allowed_hosts),
            allowed_origins=list(settings.http_allowed_origins),
        ),
    )
    app.add_middleware(
        _McpRequestAuthenticationMiddleware,
        auth_mode=os.getenv("AI_GOVERNANCE_AUTH_MODE", "development").strip().lower(),
        protected_resource_url=settings.protected_resource_url,
        canonical_server=canonical_server,
    )
    if settings.http_allowed_origins:
        # Browser tools such as the local MCP Inspector need a CORS preflight
        # before they can send Authorization. Origins remain explicit and no
        # cookies/credentialed browser requests are enabled.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.http_allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Accept",
                "MCP-Protocol-Version",
                "MCP-Method",
                "MCP-Name",
                "MCP-Session-Id",
                "Last-Event-ID",
            ],
        )
    return app


def _register_tool_schema(
    mcp: MCPServer,
    name: str,
    description: str,
    input_schema: dict[str, Any],
) -> None:
    # The SDK owns protocol framing.  Tool validation is still performed by the
    # canonical ToolRegistry, whose Pydantic model supplies this exact schema.
    async def invoke(**arguments: Any) -> dict[str, Any]:
        del arguments
        return {}

    mcp.add_tool(invoke, name=name, description=description)
    tool = mcp._tool_manager.get_tool(name)  # SDK registry; no duplicate tool list.
    assert tool is not None
    tool.parameters = input_schema


def _mcp_tool_name(canonical_name: str) -> str:
    """Convert a Core registry name into a portable MCP protocol name.

    Core names use dots as a namespace separator (for example,
    ``evaluation.get``), but clients such as VS Code accept only letters,
    numbers, underscores, and hyphens in MCP tool names. The HTTP transport
    exposes the normalized name and resolves it back to the canonical name
    before invoking the registry.
    """
    return re.sub(r"[^a-z0-9_-]", "_", canonical_name.lower())


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        return None
    return token.strip()


def _authentication_error(
    code: str,
    message: str,
    *,
    status_code: int = 401,
    protected_resource_url: str,
) -> JSONResponse:
    metadata_url = _protected_resource_metadata_url(protected_resource_url)
    headers = (
        {"WWW-Authenticate": f'Bearer resource_metadata="{metadata_url}"'}
        if status_code == 401
        else {}
    )
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
        headers=headers,
    )


def _oidc_issuer() -> str:
    issuer = os.getenv("AI_GOVERNANCE_OIDC_ISSUER", "").strip().rstrip("/")
    if not issuer:
        raise ValueError("AI_GOVERNANCE_OIDC_ISSUER is required when AI_GOVERNANCE_AUTH_MODE=keycloak")
    return issuer


def _protected_resource_metadata_path(resource_path: str) -> str:
    return f"/.well-known/oauth-protected-resource{resource_path}"


def _protected_resource_metadata_url(resource_url: str) -> str:
    scheme, separator, remainder = resource_url.partition("://")
    if not separator:
        raise ValueError("AI_GOVERNANCE_MCP_PUBLIC_URL must be an absolute URL.")
    host, separator, path = remainder.partition("/")
    if not host:
        raise ValueError("AI_GOVERNANCE_MCP_PUBLIC_URL must include a host.")
    suffix = f"/{path}" if separator else ""
    return f"{scheme}://{host}/.well-known/oauth-protected-resource{suffix}"


def _protected_resource_metadata_path_from_url(resource_url: str) -> str:
    metadata_url = _protected_resource_metadata_url(resource_url)
    _, _, path = metadata_url.partition("://")
    _, _, path = path.partition("/")
    return f"/{path}"


def _host_patterns(hosts: tuple[str, ...]) -> list[str]:
    patterns: list[str] = []
    for host in hosts:
        patterns.append(host)
        if ":" not in host or host.count(":") == 1:
            patterns.append(f"{host}:*")
    return patterns
