"""Version 1 identity-resolution extension contract."""

from __future__ import annotations

from typing import Protocol

from kavach.spi.context import TenantContext


class IdentityProvider(Protocol):
    """Version 1 identity-resolution SPI for tenant-aware identity adapters.

    The caller provides both the subject and tenancy scope so a provider can
    resolve roles, claims, or directory attributes without relying on ambient
    request globals. Returned data must be safe for the consuming contract and
    must not include authentication secrets.
    """
    def resolve(self, subject: str, *, tenant: TenantContext) -> dict[str, object]:
        """Resolve ``subject`` to contract-safe attributes for ``tenant``."""
        ...


__all__ = ["IdentityProvider"]
