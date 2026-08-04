"""Authentication contexts used by MCP calls to the REST control plane."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class McpAuthenticationContext(Protocol):
    """Supplies an optional Authorization header for one REST invocation."""

    def authorization_header(self) -> str | None: ...


@dataclass(frozen=True)
class StaticBearerAuthenticationContext:
    token: str | None

    def authorization_header(self) -> str | None:
        return f"Bearer {self.token}" if self.token else None


@dataclass(frozen=True)
class InboundRequestAuthenticationContext:
    """The already-validated bearer credential from an MCP HTTP request."""

    authorization: str

    def authorization_header(self) -> str:
        return self.authorization


@dataclass(frozen=True)
class ClientCredentialsAuthenticationContext:
    token_provider: Callable[[], str | None]

    def authorization_header(self) -> str | None:
        token = self.token_provider()
        return f"Bearer {token}" if token else None


class DevelopmentAuthenticationContext:
    """Development mode has no bearer credential to forward."""

    def authorization_header(self) -> None:
        return None
