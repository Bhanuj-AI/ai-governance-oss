from __future__ import annotations

import json
import logging
import os
import sys
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from kavach.mcp.audit import (
    MCPExecutionAuditLog,
    reset_audit_persistence,
    set_audit_persistence,
)
from kavach.mcp.clients import RestClient
from kavach.mcp.dto import ToolCallResult, ToolDescription
from kavach.mcp.exceptions import map_exception
from kavach.mcp.handlers.control_plane_tools import register_control_plane_tools
from kavach.mcp.handlers.evaluation_tools import register_evaluation_tools
from kavach.mcp.handlers.experiment_tools import register_experiment_tools
from kavach.mcp.handlers.governance_tools import register_governance_tools
from kavach.mcp.handlers.job_tools import register_job_tools
from kavach.mcp.handlers.mcp_audit_tools import register_mcp_audit_tools
from kavach.mcp.handlers.ontology_graph_tools import (
    register_ontology_graph_tools,
)
from kavach.mcp.handlers.provider_tools import register_provider_tools
from kavach.mcp.handlers.registry_tools import register_registry_tools
from kavach.mcp.handlers.replay_tools import register_replay_tools
from kavach.mcp.handlers.settings_tools import register_settings_tools
from kavach.mcp.handlers.write_tools import register_write_tools
from kavach.mcp.invocation_audit import MCPInvocationAuditLog, MCPInvocationAuditRecord
from kavach.mcp.observability import MCPMetrics
from kavach.mcp.plugins import MCPToolPlugin, initialize_mcp_tool_plugins
from kavach.mcp.registry import ToolRegistry
from kavach.mcp.runtime_context import get_runtime_context
from kavach.tenancy.domain import ActorType, AuthenticatedPrincipal
from kavach.version import __version__

logger = logging.getLogger("kavach.mcp")


@dataclass(frozen=True)
class MCPSettings:
    api_url: str
    api_timeout: float
    api_retries: int
    log_level: str
    audit_repository: str
    audit_database_path: str | None
    audit_postgres_dsn: str | None
    transport: str
    http_host: str
    http_port: int
    http_path: str
    http_allowed_hosts: tuple[str, ...]
    http_allowed_origins: tuple[str, ...]
    http_stateless: bool
    http_json_response: bool
    protected_resource_url: str


def get_mcp_settings() -> MCPSettings:
    transport = os.getenv("KAVACH_MCP_TRANSPORT", "stdio").strip().lower()
    if transport not in {"stdio", "streamable-http"}:
        raise ValueError("KAVACH_MCP_TRANSPORT must be 'stdio' or 'streamable-http'.")
    http_path = os.getenv("KAVACH_MCP_HTTP_PATH", "/mcp").strip() or "/mcp"
    if not http_path.startswith("/"):
        raise ValueError("KAVACH_MCP_HTTP_PATH must start with '/'.")
    public_url = os.getenv("KAVACH_MCP_PUBLIC_URL", "http://localhost:8002").strip()
    if not public_url:
        raise ValueError("KAVACH_MCP_PUBLIC_URL must not be empty.")
    protected_resource_url = f"{public_url.rstrip('/')}{http_path}"
    return MCPSettings(
        api_url=os.getenv("KAVACH_API_URL", "http://127.0.0.1:8000"),
        api_timeout=float(os.getenv("KAVACH_API_TIMEOUT", "10")),
        api_retries=int(os.getenv("KAVACH_API_RETRIES", "0")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        audit_repository=os.getenv("KAVACH_MCP_AUDIT_REPOSITORY", "sqlite")
        .strip()
        .lower(),
        audit_database_path=os.getenv(
            "KAVACH_MCP_AUDIT_DATABASE_PATH",
            ".kavach/mcp_execution_audit.db",
        ),
        audit_postgres_dsn=os.getenv("KAVACH_MCP_AUDIT_POSTGRES_DSN"),
        transport=transport,
        http_host=os.getenv("KAVACH_MCP_HTTP_HOST", "127.0.0.1").strip(),
        http_port=int(os.getenv("KAVACH_MCP_HTTP_PORT", "8002")),
        http_path=http_path,
        http_allowed_hosts=_split_csv_env(
            "KAVACH_MCP_HTTP_ALLOWED_HOSTS", "localhost,127.0.0.1"
        ),
        http_allowed_origins=_split_csv_env("KAVACH_MCP_HTTP_ALLOWED_ORIGINS", ""),
        http_stateless=_bool_env("KAVACH_MCP_HTTP_STATELESS", True),
        http_json_response=_bool_env("KAVACH_MCP_HTTP_JSON_RESPONSE", True),
        protected_resource_url=protected_resource_url,
    )


class KavachMCPServer:
    """
    Stateless MCP server facade for read-first Kavach tool calls.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        metrics: MCPMetrics | None = None,
        audit_log: MCPExecutionAuditLog | None = None,
        invocation_audit_log: MCPInvocationAuditLog | None = None,
        dry_run_resolver: Any | None = None,
        audit_required_resolver: Any | None = None,
        idempotency_expiry_resolver: Any | None = None,
        principal: AuthenticatedPrincipal | None = None,
    ) -> None:
        self._registry = registry
        self._metrics = metrics or MCPMetrics()
        self._audit_log = audit_log or MCPExecutionAuditLog()
        self._invocation_audit_log = invocation_audit_log or MCPInvocationAuditLog()
        self._dry_run_resolver = dry_run_resolver
        self._audit_required_resolver = audit_required_resolver
        self._idempotency_expiry_resolver = idempotency_expiry_resolver
        self._principal = principal or _development_principal()
        self._idempotency_cache: dict[
            tuple[str, str, str, str], tuple[float, str, Any]
        ] = {}

    @property
    def metrics(self) -> MCPMetrics:
        return self._metrics

    @property
    def audit_log(self) -> MCPExecutionAuditLog:
        return self._audit_log

    @property
    def invocation_audit_log(self) -> MCPInvocationAuditLog:
        """Durable evidence of every MCP invocation, including reads."""
        return self._invocation_audit_log

    def list_tools(self) -> list[ToolDescription]:
        return self._registry.list_tools()

    def call_tool(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
    ) -> ToolCallResult:
        request_id = str(uuid4())
        started_at = perf_counter()
        self._metrics.begin_tool()
        invocation_record: MCPInvocationAuditRecord | None = None

        try:
            resolved_payload = dict(payload or {})
            invocation_record = self._begin_invocation_audit(name, resolved_payload)
            controlled_fields = {"request_id", "idempotency_key", "reason"}
            if (
                self._dry_run_resolver is not None
                and "dry_run" not in resolved_payload
                and controlled_fields <= resolved_payload.keys()
            ):
                resolved_payload["dry_run"] = self._dry_run_resolver(resolved_payload)
            cache_key = None
            fingerprint = None
            cached_data = None
            if controlled_fields <= resolved_payload.keys():
                context = _mapping(resolved_payload.get("context"))
                cache_key = (
                    name,
                    str(resolved_payload["idempotency_key"]),
                    str(context.get("organization_id", "")),
                    str(context.get("project_id", "")),
                )
                fingerprint = _idempotency_fingerprint(resolved_payload)
                expiry_value = (
                    self._idempotency_expiry_resolver(resolved_payload)
                    if self._idempotency_expiry_resolver is not None
                    else "24h"
                )
                expiry_seconds = _duration_seconds(str(expiry_value))
                cached = self._idempotency_cache.get(cache_key)
                if cached and time() - cached[0] <= expiry_seconds:
                    if cached[1] != fingerprint:
                        raise ValueError(
                            "MCP idempotency key was reused with different input."
                        )
                    cached_data = cached[2]
                elif cached:
                    del self._idempotency_cache[cache_key]
            audit_required = True
            if (
                self._audit_required_resolver is not None
                and controlled_fields <= resolved_payload.keys()
            ):
                audit_required = bool(self._audit_required_resolver(resolved_payload))
            audit_token = set_audit_persistence(audit_required)
            try:
                data = (
                    cached_data
                    if cached_data is not None
                    else self._registry.call(name, resolved_payload)
                )
            finally:
                reset_audit_persistence(audit_token)
            if (
                cache_key is not None
                and fingerprint is not None
                and cached_data is None
            ):
                self._idempotency_cache[cache_key] = (time(), fingerprint, data)
            duration_ms = (perf_counter() - started_at) * 1000
            self._metrics.finish_tool(duration_ms)
            self._log_tool_call(
                tool=name,
                request_id=request_id,
                status="ok",
                duration_ms=duration_ms,
                error=None,
            )
            self._complete_invocation_audit(
                invocation_record,
                status="SUCCEEDED",
                authorization_decision="ALLOWED",
                response=data,
            )
            return ToolCallResult(
                tool=name,
                status="ok",
                data=data,
                request_id=request_id,
            )
        except Exception as exc:
            duration_ms = (perf_counter() - started_at) * 1000
            error = map_exception(exc)
            self._metrics.fail_tool()
            self._metrics.finish_tool(duration_ms)
            self._log_tool_call(
                tool=name,
                request_id=request_id,
                status="error",
                duration_ms=duration_ms,
                error=error.code,
            )
            invocation_status = "DENIED" if _is_denied(error.code) else "FAILED"
            self._complete_invocation_audit(
                invocation_record,
                status=invocation_status,
                authorization_decision="DENIED"
                if invocation_status == "DENIED"
                else "ALLOWED",
                error_category=error.code,
            )
            return ToolCallResult(
                tool=name,
                status="error",
                error=error.to_payload(),
                request_id=request_id,
            )

    def handle_json_rpc(
        self,
        message: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """
        Handle the minimal MCP JSON-RPC methods exposed in Phase 1.
        """

        method = message.get("method")
        message_id = message.get("id")

        if method == "notifications/initialized":
            return None

        try:
            if method == "initialize":
                result: dict[str, Any] = {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "kavach",
                        "version": __version__,
                    },
                    "capabilities": {
                        "tools": {},
                    },
                }
            elif method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.input_schema,
                        }
                        for tool in self.list_tools()
                    ]
                }
            elif method == "tools/call":
                params = _mapping(message.get("params"))
                tool_result = self.call_tool(
                    str(params.get("name", "")),
                    _mapping(params.get("arguments")),
                )
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                tool_result.model_dump(mode="json"),
                            ),
                        }
                    ],
                    "isError": tool_result.status == "error",
                }
            else:
                return _json_rpc_error(
                    message_id,
                    code=-32601,
                    message=f"Method '{method}' is not supported.",
                )

            return {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": result,
            }
        except Exception as exc:
            error = map_exception(exc)
            return _json_rpc_error(
                message_id,
                code=-32603,
                message=error.message,
                data=error.to_payload(),
            )

    def run_stdio(self) -> None:
        """
        Run a line-delimited JSON-RPC stdio loop for local MCP clients.
        """

        for line in sys.stdin:
            if not line.strip():
                continue

            response = self.handle_json_rpc(json.loads(line))
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

    def _log_tool_call(
        self,
        *,
        tool: str,
        request_id: str,
        status: str,
        duration_ms: float,
        error: str | None,
    ) -> None:
        runtime = get_runtime_context()
        logger.info(
            "mcp_tool_invocation",
            extra={
                "tool": tool,
                "request_id": request_id,
                "status": status,
                "duration_ms": round(duration_ms, 3),
                "error": error,
                "transport": self._metrics.transport,
                "actor_id": runtime.principal.subject
                if runtime and runtime.principal
                else None,
                "correlation_id": runtime.correlation_id if runtime else None,
            },
        )

    def _begin_invocation_audit(
        self, tool_name: str, payload: Mapping[str, Any]
    ) -> MCPInvocationAuditRecord | None:
        """Best-effort only: audit availability cannot affect a tool call."""
        runtime = get_runtime_context()
        context = _mapping(payload.get("context"))
        principal = runtime.principal if runtime else None
        request_id = (
            str(payload.get("request_id"))
            if payload.get("request_id")
            else (
                runtime.request_id if runtime and runtime.request_id else str(uuid4())
            )
        )
        correlation_id = (
            str(payload.get("correlation_id"))
            if payload.get("correlation_id")
            else (
                runtime.correlation_id
                if runtime and runtime.correlation_id
                else request_id
            )
        )
        # A caller that retries a logical request must supply its stable
        # request_id; the UPSERT then updates the same invocation evidence.
        invocation_id = request_id
        try:
            return self._invocation_audit_log.received(
                invocation_id=invocation_id,
                request_id=request_id,
                correlation_id=correlation_id,
                tool_name=tool_name,
                organization_id=str(
                    context.get("organization_id")
                    or (principal.organization_id if principal else None)
                    or os.getenv("KAVACH_BOOTSTRAP_ORGANIZATION_ID", "org_default")
                ),
                project_id=(
                    str(context["project_id"]) if context.get("project_id") else None
                ),
                actor_id=principal.subject
                if principal
                else (runtime.development_actor_id if runtime else None),
                actor_type=(principal.principal_type.value if principal else None),
                client_id=principal.client_id if principal else None,
                authorization_decision="ALLOWED",
                payload=payload,
            )
        except Exception:
            logger.exception(
                "mcp_invocation_audit_write_failed", extra={"tool": tool_name}
            )
            return None

    def _complete_invocation_audit(
        self,
        record: MCPInvocationAuditRecord | None,
        *,
        status: str,
        authorization_decision: str,
        response: Any = None,
        error_category: str | None = None,
    ) -> None:
        if record is None:
            return
        try:
            self._invocation_audit_log.complete(
                record,
                status=status,
                authorization_decision=authorization_decision,
                response=response,
                error_category=error_category,
            )
        except Exception:
            logger.exception(
                "mcp_invocation_audit_write_failed", extra={"tool": record.tool_name}
            )


def create_server(
    rest_client: RestClient | None = None,
    audit_log: MCPExecutionAuditLog | None = None,
    invocation_audit_log: MCPInvocationAuditLog | None = None,
    principal: AuthenticatedPrincipal | None = None,
    mcp_plugins: Iterable[MCPToolPlugin] = (),
) -> KavachMCPServer:
    settings = get_mcp_settings()
    logging.getLogger("kavach.mcp").setLevel(settings.log_level.upper())

    metrics = MCPMetrics()
    resolved_audit_log = audit_log or _create_audit_log(settings)
    resolved_invocation_audit_log = (
        invocation_audit_log or _create_invocation_audit_log(settings)
    )
    client = rest_client or RestClient(
        base_url=settings.api_url,
        timeout=settings.api_timeout,
        retries=settings.api_retries,
        default_headers=_api_headers(),
        auth_provider=_keycloak_token_provider(),
    )
    registry = ToolRegistry()

    register_provider_tools(registry, client, metrics)
    register_registry_tools(registry, client, metrics)
    register_evaluation_tools(registry, client, metrics)
    register_experiment_tools(registry, client, metrics)
    register_replay_tools(registry, client, metrics)
    register_governance_tools(registry, client, metrics)
    register_job_tools(registry, client, metrics)
    register_mcp_audit_tools(registry, client, metrics)
    register_ontology_graph_tools(registry, client, metrics)
    register_write_tools(registry, client, metrics, resolved_audit_log)
    register_control_plane_tools(
        registry,
        client,
        metrics,
        resolved_audit_log,
        principal or _development_principal(),
    )
    register_settings_tools(registry, client, metrics, resolved_audit_log)
    initialize_mcp_tool_plugins(registry, client, metrics, mcp_plugins)

    return KavachMCPServer(
        registry=registry,
        metrics=metrics,
        audit_log=resolved_audit_log,
        invocation_audit_log=resolved_invocation_audit_log,
        dry_run_resolver=lambda payload: _resolve_dry_run_default(
            client, metrics, payload
        ),
        audit_required_resolver=lambda payload: _resolve_operational_setting(
            client, metrics, payload, "mcp.audit_required", True
        ),
        idempotency_expiry_resolver=lambda payload: _resolve_operational_setting(
            client, metrics, payload, "mcp.idempotency_expiry", "24h"
        ),
        principal=principal,
    )


def _development_principal() -> AuthenticatedPrincipal:
    actor_id = os.getenv("KAVACH_DEVELOPMENT_ACTOR_ID")
    return AuthenticatedPrincipal(
        subject=actor_id,
        principal_type=ActorType.SYSTEM,
        organization_id=None,
        client_id="development",
        issuer="development",
    )


def _api_headers() -> dict[str, str]:
    """Return optional headers used when MCP calls a protected REST API."""
    token = os.getenv("KAVACH_API_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _keycloak_token_provider() -> Any:
    """Return a cached client-credentials token provider for long-lived MCP."""
    if os.getenv("KAVACH_API_TOKEN", "").strip():
        return None
    token_url = os.getenv("KAVACH_MCP_TOKEN_URL", "").strip()
    client_id = os.getenv("KAVACH_MCP_CLIENT_ID", "").strip()
    client_secret = os.getenv("KAVACH_MCP_CLIENT_SECRET", "").strip()
    if not token_url or not client_id or not client_secret:
        return None
    state: dict[str, Any] = {"token": None, "expires_at": 0.0}
    lock = threading.Lock()

    def provider() -> str | None:
        now = time()
        with lock:
            if state["token"] and now < state["expires_at"] - 30:
                return state["token"]
            body = urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                }
            ).encode()
            with urlopen(
                Request(
                    token_url,
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                ),
                timeout=10,
            ) as response:
                payload = json.load(response)
            state["token"] = payload["access_token"]
            state["expires_at"] = now + int(payload.get("expires_in", 300))
            return state["token"]

    return provider


def _resolve_dry_run_default(
    client: RestClient, metrics: MCPMetrics, payload: Mapping[str, Any]
) -> bool:
    return bool(
        _resolve_operational_setting(
            client, metrics, payload, "mcp.dry_run_default", False
        )
    )


def _resolve_operational_setting(
    client: RestClient,
    metrics: MCPMetrics,
    payload: Mapping[str, Any],
    key: str,
    fallback: Any,
) -> Any:
    context = _mapping(payload.get("context"))
    organization_id = context.get("organization_id")
    project_id = context.get("project_id")
    scoped_client = (
        client.with_tenant_context(
            str(organization_id), str(project_id) if project_id else None
        )
        if organization_id
        else client
    )
    scope = "PROJECT" if project_id else "ORGANIZATION" if organization_id else "SYSTEM"
    metrics.record_rest_call()
    setting = scoped_client.get(f"/api/v1/settings/{key}", query={"scope": scope})
    return (
        setting.get("effective_value", fallback)
        if isinstance(setting, Mapping)
        else fallback
    )


def _idempotency_fingerprint(payload: Mapping[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {"request_id", "correlation_id"}
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"))


def _duration_seconds(value: str) -> float:
    units = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    for unit in ("ms", "s", "m", "h", "d", "w"):
        if value.endswith(unit):
            return int(value[: -len(unit)]) * units[unit]
    raise ValueError(f"Invalid MCP idempotency expiry: {value}")


def _create_audit_log(settings: MCPSettings) -> MCPExecutionAuditLog:
    if settings.audit_repository == "postgres":
        if not settings.audit_postgres_dsn:
            raise ValueError(
                "KAVACH_MCP_AUDIT_POSTGRES_DSN is required when "
                "KAVACH_MCP_AUDIT_REPOSITORY=postgres"
            )
        return MCPExecutionAuditLog.postgres(settings.audit_postgres_dsn)
    if settings.audit_repository == "sqlite":
        if not settings.audit_database_path:
            return MCPExecutionAuditLog.in_memory()
        return MCPExecutionAuditLog.sqlite(Path(settings.audit_database_path))

    raise ValueError("KAVACH_MCP_AUDIT_REPOSITORY must be sqlite or postgres")


def _create_invocation_audit_log(settings: MCPSettings) -> MCPInvocationAuditLog:
    """Use the same backend configuration but a distinct invocation table."""
    if settings.audit_repository == "postgres":
        if not settings.audit_postgres_dsn:
            raise ValueError(
                "KAVACH_MCP_AUDIT_POSTGRES_DSN is required when "
                "KAVACH_MCP_AUDIT_REPOSITORY=postgres"
            )
        return MCPInvocationAuditLog.postgres(settings.audit_postgres_dsn)
    if settings.audit_repository == "sqlite":
        if not settings.audit_database_path:
            return MCPInvocationAuditLog.in_memory()
        return MCPInvocationAuditLog.sqlite(Path(settings.audit_database_path))
    raise ValueError("KAVACH_MCP_AUDIT_REPOSITORY must be sqlite or postgres")


def _is_denied(error_code: str) -> bool:
    normalized = error_code.upper()
    return (
        "DENIED" in normalized
        or "FORBIDDEN" in normalized
        or "UNAUTHORIZED" in normalized
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _split_csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        item.strip() for item in os.getenv(name, default).split(",") if item.strip()
    )


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _json_rpc_error(
    message_id: Any,
    *,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": error,
    }
