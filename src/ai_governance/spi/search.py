"""Version 1 search-provider contract for future search implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ai_governance.spi.context import TenantContext


@dataclass(frozen=True)
class SearchRequest:
    """Tenant-scoped request passed to a :class:`SearchProvider`.

    ``cursor`` is opaque to AI Governance Control Plane and must be interpreted only by the provider
    that issued it. Providers must apply the supplied tenant scope before
    evaluating the query and must never silently broaden it.
    """
    query: str
    tenant: TenantContext
    limit: int = 25
    cursor: str | None = None


@dataclass(frozen=True)
class SearchResult:
    """Stable, provider-neutral search page returned by a search SPI.

    Items intentionally remain JSON-compatible dictionaries until OSS defines
    a first-class cross-plane search result schema. Provider-specific metadata
    belongs in ``metadata`` and must not contain credentials or tenant data
    outside the request scope.
    """
    items: tuple[dict[str, object], ...]
    next_cursor: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class SearchProvider(Protocol):
    """Version 1 search SPI owned by AI Governance Control Plane OSS.

    Implementations can index OSS assets, Neo4j data, or an external enterprise
    search service, but must preserve request tenant isolation and return the
    stable :class:`SearchResult` shape. Implement the contract by composition;
    plugins should register it through ``context.providers`` rather than
    replacing a service method.
    """

    def search(self, request: SearchRequest) -> SearchResult:
        """Return one deterministic, tenant-isolated page for ``request``."""
        ...


__all__ = ["SearchProvider", "SearchRequest", "SearchResult"]
