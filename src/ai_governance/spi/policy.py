"""Version 1 policy-evaluation extension contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from ai_governance.spi.context import TenantContext


class PolicyProvider(Protocol):
    """Version 1 policy-evaluation SPI for deterministic policy engines.

    Implementations receive evidence and explicit tenant context, then return a
    JSON-compatible outcome owned by the policy contract. They must not infer
    tenancy from global state or mutate the caller's evidence mapping.
    """
    def evaluate(
        self, evidence: Mapping[str, object], *, tenant: TenantContext
    ) -> Mapping[str, object]:
        """Evaluate caller-owned evidence in the supplied tenant boundary."""
        ...


__all__ = ["PolicyProvider"]
