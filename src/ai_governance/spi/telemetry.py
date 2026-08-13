"""Public, provider-neutral telemetry delivery contract."""

from __future__ import annotations

from typing import Protocol

from ai_governance.domain.telemetry import TelemetryExportResult, TelemetrySnapshot


class TelemetryExporter(Protocol):
    """Deliver one sanitized aggregate snapshot without raising to callers."""

    def export(self, snapshot: TelemetrySnapshot) -> TelemetryExportResult: ...
