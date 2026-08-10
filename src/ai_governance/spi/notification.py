"""Version 1 notification extension contract."""

from collections.abc import Mapping
from typing import Protocol

from ai_governance.spi.context import TenantContext


class NotificationProvider(Protocol):
    """Version 1 notification SPI for tenant-aware outbound delivery.

    The message is deliberately a mapping until a versioned notification
    envelope is introduced. Providers must treat it as caller-owned input and
    route delivery using only the supplied tenant context and declared plugin
    configuration.
    """
    def notify(self, message: Mapping[str, object], *, tenant: TenantContext) -> None:
        """Deliver a caller-owned message within the supplied tenant boundary."""
        ...


__all__ = ["NotificationProvider"]
