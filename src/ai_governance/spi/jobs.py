"""Version 1 asynchronous-job extension contract."""

from collections.abc import Mapping
from typing import Protocol

from ai_governance.spi.context import TenantContext


class JobProvider(Protocol):
    """Version 1 asynchronous-job SPI for an external execution backend.

    ``submit`` returns the provider's immutable job reference. The provider
    must retain tenant isolation and leave orchestration, idempotency policy,
    and AI Governance Control Plane domain lifecycle ownership with the calling control plane.
    """
    def submit(self, job: Mapping[str, object], *, tenant: TenantContext) -> str:
        """Submit a tenant-scoped job and return its immutable provider reference."""
        ...


__all__ = ["JobProvider"]
