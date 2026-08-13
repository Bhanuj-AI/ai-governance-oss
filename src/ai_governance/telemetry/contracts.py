"""Narrow recording contract used by runtime services without exporter knowledge."""

from __future__ import annotations

from typing import Protocol

from ai_governance.domain.telemetry import TelemetryMetric


class TelemetryCollector(Protocol):
    """Best-effort local aggregate recorder; never a network client."""

    def record(self, metric: TelemetryMetric, *, duration_ms: int | None = None) -> None: ...
