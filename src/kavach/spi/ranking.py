"""Version 1 result-ranking extension contract."""

from collections.abc import Sequence
from typing import Protocol, TypeVar

from kavach.spi.context import TenantContext

Item = TypeVar("Item")


class RankingProvider(Protocol[Item]):
    """Version 1 ranking SPI that preserves item identity and tenant scope.

    A ranking provider may reorder or score the supplied items but must not
    synthesize a cross-tenant result set. The generic item type lets OSS evolve
    the owning plane's result model independently of this extension boundary.
    """
    def rank(self, items: Sequence[Item], *, tenant: TenantContext) -> Sequence[Item]:
        """Return the supplied items in provider-selected order for ``tenant``."""
        ...


__all__ = ["RankingProvider"]
