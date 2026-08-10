"""Version 1 extension contract for external object storage."""

from typing import Protocol

from ai_governance.spi.context import TenantContext


class StorageProvider(Protocol):
    """Version 1 byte-object storage SPI for tenant-isolated external stores.

    Implementations own backend-specific naming, encryption, and transport;
    callers own the stable object key contract. Both operations receive tenant
    context explicitly so a provider can enforce namespace isolation.
    """
    def get(self, key: str, *, tenant: TenantContext) -> bytes:
        """Read the tenant-scoped object identified by the caller-owned key."""
        ...

    def put(self, key: str, value: bytes, *, tenant: TenantContext) -> None:
        """Write bytes under the tenant-scoped caller-owned object key."""
        ...


__all__ = ["StorageProvider"]
