"""Request-local MCP identity and forwarding state.

Context variables provide task-local isolation for Streamable HTTP requests;
they must never be replaced with process-global mutable token state.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass, field

from ai_governance.mcp.authentication import McpAuthenticationContext
from ai_governance.tenancy.domain import AuthenticatedPrincipal


@dataclass(frozen=True)
class McpRuntimeContext:
    authentication: McpAuthenticationContext
    principal: AuthenticatedPrincipal | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    development_actor_id: str | None = None
    inbound_headers: Mapping[str, str] = field(default_factory=dict)


_runtime_context: ContextVar[McpRuntimeContext | None] = ContextVar(
    "ai_governance_mcp_runtime_context", default=None
)


def get_runtime_context() -> McpRuntimeContext | None:
    return _runtime_context.get()


def set_runtime_context(context: McpRuntimeContext) -> Token[McpRuntimeContext | None]:
    return _runtime_context.set(context)


def reset_runtime_context(token: Token[McpRuntimeContext | None]) -> None:
    _runtime_context.reset(token)
