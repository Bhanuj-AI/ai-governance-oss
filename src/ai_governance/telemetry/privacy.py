"""Allow-list validation for the only telemetry payload that may leave BHANUJ."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ai_governance.domain.telemetry import TelemetryMetric, TelemetrySnapshot


class TelemetryPrivacyError(ValueError):
    pass


class TelemetryPrivacyGuard:
    """Reject unknown fields instead of trying to redact customer data."""

    _ENVELOPE_FIELDS = frozenset({
        "schema_version", "installation_id", "ai_governance_version", "period_start",
        "period_end", "category", "metrics", "distributions",
    })
    _DISTRIBUTION_FIELDS = frozenset({
        "count", "min_ms", "max_ms", "le_10ms", "le_100ms", "le_1s",
        "le_10s", "le_60s", "gt_60s",
    })
    _DISTRIBUTIONS = frozenset({
        "job_execution_duration", "evaluation_duration", "replay_duration",
        "impact_simulation_duration",
    })

    def serialize(self, snapshot: TelemetrySnapshot) -> dict[str, object]:
        payload = snapshot.as_payload()
        self.validate_payload(payload)
        return payload

    def validate_payload(self, payload: Mapping[str, Any]) -> None:
        if set(payload) != self._ENVELOPE_FIELDS:
            raise TelemetryPrivacyError("Telemetry payload contains an unapproved field.")
        if not isinstance(payload["metrics"], Mapping) or not isinstance(payload["distributions"], Mapping):
            raise TelemetryPrivacyError("Telemetry aggregates must be objects.")
        if not set(payload["metrics"]).issubset({metric.value for metric in TelemetryMetric}):
            raise TelemetryPrivacyError("Telemetry payload contains an unapproved metric.")
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in payload["metrics"].values()):
            raise TelemetryPrivacyError("Telemetry counters must be non-negative integers.")
        if not set(payload["distributions"]).issubset(self._DISTRIBUTIONS):
            raise TelemetryPrivacyError("Telemetry payload contains an unapproved distribution.")
        for distribution in payload["distributions"].values():
            if not isinstance(distribution, Mapping) or set(distribution) != self._DISTRIBUTION_FIELDS:
                raise TelemetryPrivacyError("Telemetry payload contains an invalid distribution.")
            if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in distribution.values()):
                raise TelemetryPrivacyError("Telemetry distributions must contain non-negative integers.")
