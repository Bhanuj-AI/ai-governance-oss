from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from ai_governance.domain.telemetry import (
    DurationHistogram,
    TelemetryCategory,
    TelemetryExportResult,
    TelemetryMetric,
    TelemetryMode,
    TelemetryPolicy,
    TelemetrySnapshot,
)
from ai_governance.services.telemetry_service import TelemetryService
from ai_governance.telemetry.privacy import TelemetryPrivacyError, TelemetryPrivacyGuard


class _Configuration:
    def __init__(self, **values: object) -> None:
        self.values = {
            "telemetry.mode": "standard",
            "telemetry.essential.enabled": True,
            "telemetry.product_analytics.enabled": False,
            "telemetry.performance_research.enabled": False,
            "telemetry.exporter.type": "none",
            "telemetry.aggregation_period": "1d",
            **values,
        }

    def get(self, key: str) -> object:
        return self.values[key]


class _StateRepository:
    def __init__(self) -> None:
        self.value = None
        self.version = 0

    def load(self):
        return self.value, self.version

    def save(self, value, expected_version: int) -> int:
        assert expected_version == self.version
        self.value = value
        self.version += 1
        return self.version


class _Exporter:
    def __init__(self, result: TelemetryExportResult) -> None:
        self.result = result
        self.calls = 0

    def export(self, snapshot: TelemetrySnapshot) -> TelemetryExportResult:
        self.calls += 1
        return self.result


def _snapshot() -> TelemetrySnapshot:
    return TelemetrySnapshot(
        installation_id="81eb1e84-0000-4000-8000-000000000000",
        ai_governance_version="1.0.0",
        period_start=datetime(2026, 8, 13, tzinfo=UTC),
        period_end=datetime(2026, 8, 14, tzinfo=UTC),
        category=TelemetryCategory.PRODUCT_ANALYTICS,
        metrics=((TelemetryMetric.GOVERNED_EXECUTIONS, 12),),
    )


def test_snapshot_schema_is_immutable_and_versioned() -> None:
    snapshot = _snapshot()

    assert snapshot.as_payload()["schema_version"] == "1"
    with pytest.raises(FrozenInstanceError):
        snapshot.ai_governance_version = "other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="Unsupported telemetry schema"):
        TelemetrySnapshot(
            installation_id=snapshot.installation_id,
            ai_governance_version="1.0.0",
            period_start=snapshot.period_start,
            period_end=snapshot.period_end,
            category=TelemetryCategory.ESSENTIAL,
            schema_version="2",
        )
    with pytest.raises(ValueError, match="not arbitrary text"):
        TelemetrySnapshot(
            installation_id=snapshot.installation_id,
            ai_governance_version="prompt: customer secret",
            period_start=snapshot.period_start,
            period_end=snapshot.period_end,
            category=TelemetryCategory.ESSENTIAL,
        )


@pytest.mark.parametrize("field", ["prompt", "response", "email", "tenant_name", "project_name", "api_key", "metadata"])
def test_privacy_guard_rejects_prohibited_or_arbitrary_fields(field: str) -> None:
    payload = _snapshot().as_payload()
    payload[field] = "customer-content"

    with pytest.raises(TelemetryPrivacyError):
        TelemetryPrivacyGuard().validate_payload(payload)


def test_policy_enforces_each_category() -> None:
    assert TelemetryPolicy().allows(TelemetryCategory.ESSENTIAL)
    assert not TelemetryPolicy().allows(TelemetryCategory.PRODUCT_ANALYTICS)
    assert not TelemetryPolicy().allows(TelemetryCategory.PERFORMANCE_RESEARCH)
    assert not TelemetryPolicy(mode=TelemetryMode.DISABLED).allows(TelemetryCategory.ESSENTIAL)
    assert TelemetryPolicy(product_analytics_enabled=True).allows(TelemetryCategory.PRODUCT_ANALYTICS)
    assert TelemetryPolicy(performance_research_enabled=True).allows(TelemetryCategory.PERFORMANCE_RESEARCH)


@pytest.mark.parametrize(
    ("essential", "product", "performance"),
    [
        (False, False, False), (False, False, True), (False, True, False), (False, True, True),
        (True, False, False), (True, False, True), (True, True, False), (True, True, True),
    ],
)
def test_policy_applies_every_category_combination(essential: bool, product: bool, performance: bool) -> None:
    policy = TelemetryPolicy(essential_enabled=essential, product_analytics_enabled=product, performance_research_enabled=performance)

    assert policy.allows(TelemetryCategory.ESSENTIAL) is essential
    assert policy.allows(TelemetryCategory.PRODUCT_ANALYTICS) is product
    assert policy.allows(TelemetryCategory.PERFORMANCE_RESEARCH) is performance


def test_local_aggregation_is_bounded_and_preview_is_sanitized() -> None:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    service = TelemetryService(
        _StateRepository(),
        _Configuration(**{
            "telemetry.product_analytics.enabled": True,
            "telemetry.performance_research.enabled": True,
        }),
        clock=lambda: now,
    )
    service.record(TelemetryMetric.EVALUATION_RUNS, duration_ms=101)
    service.record(TelemetryMetric.EVALUATION_RUNS, duration_ms=9)

    payloads = service.preview()
    usage = next(item for item in payloads if item["category"] == "PRODUCT_ANALYTICS")
    performance = next(item for item in payloads if item["category"] == "PERFORMANCE_RESEARCH")
    assert usage["metrics"] == {"evaluation_runs": 2}
    assert performance["distributions"]["evaluation_duration"]["le_10ms"] == 1
    assert performance["distributions"]["evaluation_duration"]["le_1s"] == 1
    assert "tenant_id" not in str(payloads)


def test_disabled_mode_causes_zero_outbound_requests() -> None:
    exporter = _Exporter(TelemetryExportResult(delivered=True))
    service = TelemetryService(
        _StateRepository(),
        _Configuration(**{"telemetry.mode": "disabled"}),
        exporter_factory=lambda: exporter,
    )
    service.record(TelemetryMetric.GOVERNED_EXECUTIONS)
    service.flush()

    assert exporter.calls == 0


def test_retry_is_bounded_and_export_failure_never_escapes() -> None:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    exporter = _Exporter(TelemetryExportResult(delivered=False, retryable=True, error_code="NETWORK_UNAVAILABLE"))
    service = TelemetryService(
        _StateRepository(),
        _Configuration(**{
            "telemetry.essential.enabled": False,
            "telemetry.product_analytics.enabled": True,
        }),
        exporter_factory=lambda: exporter,
        clock=lambda: now,
    )
    service.record(TelemetryMetric.GOVERNED_EXECUTIONS)
    service._state.period_start = now - timedelta(days=2)  # force a bounded period rollover
    service.flush()
    service.flush()
    service.flush()
    service.flush()

    assert exporter.calls == 4
    assert service.status()["pending_snapshots"] == 0
    assert service.metrics.dropped_snapshots_total == 1


def test_duration_histogram_is_bounded() -> None:
    histogram = DurationHistogram().observe(10).observe(101).observe(60_001)

    assert histogram.count == 3
    assert histogram.le_10ms == 1
    assert histogram.le_1s == 1
    assert histogram.gt_60s == 1


def test_installation_identity_is_stable_across_restart() -> None:
    repository = _StateRepository()
    first = TelemetryService(repository, _Configuration())
    second = TelemetryService(repository, _Configuration())

    assert first.status()["installation_id"] == second.status()["installation_id"]
