from ai_governance.domain.telemetry import TelemetryExportResult, TelemetrySnapshot


class NoneTelemetryExporter:
    """Deliberately does no outbound telemetry I/O."""

    def export(self, snapshot: TelemetrySnapshot) -> TelemetryExportResult:
        return TelemetryExportResult(delivered=False, retryable=False, error_code="EXPORTER_DISABLED")
