from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class TenancyMetrics:
    context_resolution_total: Counter[str] = field(default_factory=Counter)

    def record_context_resolution(self, result: str) -> None:
        self.context_resolution_total[result] += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "ai_governance_tenant_context_resolution_total": dict(
                self.context_resolution_total
            )
        }


METRICS = TenancyMetrics()
