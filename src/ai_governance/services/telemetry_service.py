"""Fail-open telemetry aggregation, snapshotting, and isolated delivery."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Event, RLock
from time import monotonic
from uuid import uuid4

from ai_governance.domain.telemetry import (
    DurationHistogram,
    TelemetryCategory,
    TelemetryExportResult,
    TelemetryMetric,
    TelemetryMode,
    TelemetryPolicy,
    TelemetrySnapshot,
)
from ai_governance.services.provider_installation_service import (
    EnvironmentSecretReferenceResolver,
)
from ai_governance.settings_control.operational import duration_seconds
from ai_governance.settings_control.service import ConfigurationService
from ai_governance.spi.telemetry import TelemetryExporter
from ai_governance.telemetry.exporters import (
    NoneTelemetryExporter,
    PostHogTelemetryExporter,
)
from ai_governance.telemetry.privacy import TelemetryPrivacyGuard
from ai_governance.telemetry.repository import TelemetryStateRepository
from ai_governance.version import __version__

_LOGGER = logging.getLogger(__name__)
_PRODUCT_METRICS = frozenset({
    TelemetryMetric.GOVERNED_EXECUTIONS, TelemetryMetric.EVALUATION_RUNS,
    TelemetryMetric.REPLAY_RUNS, TelemetryMetric.GOVERNANCE_DECISIONS,
    TelemetryMetric.IMPACT_SIMULATIONS, TelemetryMetric.BEHAVIOR_CONTRACTS_CREATED,
    TelemetryMetric.PROMPT_ASSETS, TelemetryMetric.MODEL_ASSETS,
    TelemetryMetric.DATASET_ASSETS, TelemetryMetric.EVALUATION_PROVIDER_ASSETS,
    TelemetryMetric.JOB_EXECUTIONS,
})
_PERFORMANCE_DISTRIBUTIONS = frozenset({
    "job_execution_duration", "evaluation_duration", "replay_duration",
    "impact_simulation_duration",
})


class TelemetryMetrics:
    """Local-only operational metrics; intentionally not sent through telemetry."""

    def __init__(self) -> None:
        self.snapshots_created_total = 0
        self.exports_total = 0
        self.export_failures_total = 0
        self.export_duration_seconds = 0.0
        self.pending_snapshots = 0
        self.dropped_snapshots_total = 0

    def snapshot(self) -> dict[str, int | float]:
        return vars(self).copy()


@dataclass
class _State:
    installation_id: str
    ai_governance_version: str
    period_start: datetime
    counters: dict[TelemetryMetric, int] = field(default_factory=dict)
    distributions: dict[str, DurationHistogram] = field(default_factory=dict)
    pending: list[tuple[TelemetrySnapshot, int]] = field(default_factory=list)
    last_export_status: str | None = None
    last_successful_export: datetime | None = None


class TelemetryService:
    """Aggregate typed facts locally; all failures are isolated from callers."""

    def __init__(
        self,
        state_repository: TelemetryStateRepository,
        configuration_service: ConfigurationService,
        exporter_factory: Callable[[], TelemetryExporter] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._state_repository = state_repository
        self._configuration = configuration_service
        self._exporter_factory = exporter_factory or self._configured_exporter
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()
        self.metrics = TelemetryMetrics()
        self._state_version = 0
        self._state = self._load_or_create()

    def policy(self) -> TelemetryPolicy:
        try:
            return TelemetryPolicy(
                mode=TelemetryMode(self._configuration.get("telemetry.mode")),
                essential_enabled=bool(self._configuration.get("telemetry.essential.enabled")),
                product_analytics_enabled=bool(self._configuration.get("telemetry.product_analytics.enabled")),
                performance_research_enabled=bool(self._configuration.get("telemetry.performance_research.enabled")),
            )
        except Exception:  # noqa: BLE001 - telemetry configuration is optional.
            return TelemetryPolicy(mode=TelemetryMode.DISABLED, essential_enabled=False)

    def record(self, metric: TelemetryMetric, *, duration_ms: int | None = None) -> None:
        """Record a named aggregate only. This method never performs network I/O."""
        category = TelemetryCategory.PRODUCT_ANALYTICS if metric in _PRODUCT_METRICS else TelemetryCategory.ESSENTIAL
        if not self.policy().allows(category):
            return
        try:
            with self._lock:
                self._rollover_if_due_locked()
                self._state.counters[metric] = self._state.counters.get(metric, 0) + 1
                if duration_ms is not None:
                    name = self._duration_name(metric)
                    if name:
                        self._state.distributions[name] = self._state.distributions.get(name, DurationHistogram()).observe(duration_ms)
                self._persist_locked()
        except Exception:  # noqa: BLE001 - telemetry must not interrupt governed work.
            _LOGGER.warning("telemetry_recording_unavailable", extra={"metric": metric.value})

    def preview(self) -> list[dict[str, object]]:
        with self._lock:
            self._rollover_if_due_locked()
            return [self._privacy_payload(snapshot) for snapshot in self._snapshots_locked(self._clock())]

    def status(self) -> dict[str, object]:
        with self._lock:
            policy = self.policy()
            return {
                "mode": policy.mode.value,
                "installation_id": self._state.installation_id,
                "enabled_categories": [category.value for category in TelemetryCategory if policy.allows(category)],
                "exporter": self._exporter_type(),
                "last_export_status": self._state.last_export_status,
                "last_successful_export": self._state.last_successful_export,
                "pending_snapshots": len(self._state.pending),
                "operational_metrics": self.metrics.snapshot(),
            }

    def flush(self) -> None:
        """Create/export bounded snapshots. A failure cannot escape the worker."""
        if self.policy().mode is TelemetryMode.DISABLED:
            with self._lock:
                dropped = len(self._state.pending)
                self._state.pending.clear()
                self.metrics.dropped_snapshots_total += dropped
                self.metrics.pending_snapshots = 0
                self._persist_locked()
            return
        try:
            with self._lock:
                self._rollover_if_due_locked()
                pending = list(self._state.pending)
            exporter = self._exporter_factory()
            retained: list[tuple[TelemetrySnapshot, int]] = []
            for snapshot, attempts in pending:
                if not self.policy().allows(snapshot.category):
                    continue
                result = self._export(exporter, snapshot)
                if not result.delivered and result.retryable and attempts < 3:
                    retained.append((snapshot, attempts + 1))
                elif not result.delivered:
                    self.metrics.dropped_snapshots_total += 1
            with self._lock:
                self._state.pending = retained
                self.metrics.pending_snapshots = len(retained)
                self._persist_locked()
        except Exception:  # noqa: BLE001 - telemetry delivery is best effort.
            _LOGGER.warning("telemetry_delivery_unavailable")

    def _rollover_if_due_locked(self) -> None:
        now = self._clock()
        period = timedelta(seconds=duration_seconds(str(self._configuration.get("telemetry.aggregation_period"))))
        if now - self._state.period_start < period:
            return
        snapshots = self._snapshots_locked(now)
        self._state.pending.extend((snapshot, 0) for snapshot in snapshots)
        if len(self._state.pending) > 30:
            dropped = len(self._state.pending) - 30
            self._state.pending = self._state.pending[-30:]
            self.metrics.dropped_snapshots_total += dropped
        self.metrics.snapshots_created_total += len(snapshots)
        self.metrics.pending_snapshots = len(self._state.pending)
        self._state.period_start = now
        self._state.counters.clear()
        self._state.distributions.clear()
        self._persist_locked()

    def _snapshots_locked(self, period_end: datetime) -> list[TelemetrySnapshot]:
        policy = self.policy()
        snapshots: list[TelemetrySnapshot] = []
        if policy.allows(TelemetryCategory.ESSENTIAL):
            essential = tuple((metric, self._state.counters.get(metric, 0)) for metric in (
                TelemetryMetric.INSTALLATION_STARTED, TelemetryMetric.INSTALLATION_UPGRADED,
            ) if self._state.counters.get(metric, 0))
            snapshots.append(self._snapshot(TelemetryCategory.ESSENTIAL, essential, ()))
        if policy.allows(TelemetryCategory.PRODUCT_ANALYTICS):
            metrics = tuple((metric, self._state.counters.get(metric, 0)) for metric in TelemetryMetric if metric in _PRODUCT_METRICS and self._state.counters.get(metric, 0))
            snapshots.append(self._snapshot(TelemetryCategory.PRODUCT_ANALYTICS, metrics, ()))
        if policy.allows(TelemetryCategory.PERFORMANCE_RESEARCH):
            distributions = tuple((name, self._state.distributions[name]) for name in sorted(self._state.distributions) if name in _PERFORMANCE_DISTRIBUTIONS)
            snapshots.append(self._snapshot(TelemetryCategory.PERFORMANCE_RESEARCH, (), distributions))
        return snapshots

    def _snapshot(self, category: TelemetryCategory, metrics, distributions) -> TelemetrySnapshot:
        return TelemetrySnapshot(
            installation_id=self._state.installation_id, ai_governance_version=self._state.ai_governance_version,
            period_start=self._state.period_start, period_end=self._clock(), category=category,
            metrics=metrics, distributions=distributions,
        )

    def _export(self, exporter: TelemetryExporter, snapshot: TelemetrySnapshot) -> TelemetryExportResult:
        self._privacy_payload(snapshot)
        started = monotonic()
        try:
            result = exporter.export(snapshot)
        except Exception:  # noqa: BLE001 - third-party exporters must not affect governance workflows.
            result = TelemetryExportResult(delivered=False, retryable=True, error_code="EXPORTER_EXCEPTION")
        self.metrics.exports_total += 1
        self.metrics.export_duration_seconds += monotonic() - started
        with self._lock:
            if result.delivered:
                self._state.last_export_status = "succeeded"
                self._state.last_successful_export = self._clock()
            else:
                self._state.last_export_status = result.error_code or "failed"
                self.metrics.export_failures_total += 1
        return result

    def _privacy_payload(self, snapshot: TelemetrySnapshot) -> dict[str, object]:
        return TelemetryPrivacyGuard().serialize(snapshot)

    def _load_or_create(self) -> _State:
        try:
            value, self._state_version = self._state_repository.load()
            if value:
                return self._decode_state(value)
        except Exception:  # noqa: BLE001 - a corrupt or unavailable telemetry store is reset safely.
            _LOGGER.warning("telemetry_state_unavailable")
        state = _State(str(uuid4()), __version__, self._clock(), {TelemetryMetric.INSTALLATION_STARTED: 1})
        self._persist_initial(state)
        return state

    def _persist_initial(self, state: _State) -> None:
        self._state = state
        self._persist_locked()

    def _persist_locked(self) -> None:
        try:
            self._state_version = self._state_repository.save(self._encode_state(), self._state_version)
        except Exception:  # noqa: BLE001 - aggregation remains best effort.
            # Aggregation remains best-effort and must not impact business workflows.
            return

    def _encode_state(self) -> dict[str, object]:
        return {
            "installation_id": self._state.installation_id, "ai_governance_version": self._state.ai_governance_version,
            "period_start": self._state.period_start.isoformat(),
            "counters": {metric.value: value for metric, value in self._state.counters.items()},
            "distributions": {name: histogram.as_payload() for name, histogram in self._state.distributions.items()},
            "pending": [{"payload": self._privacy_payload(snapshot), "attempts": attempts} for snapshot, attempts in self._state.pending],
            "last_export_status": self._state.last_export_status,
            "last_successful_export": self._state.last_successful_export.isoformat() if self._state.last_successful_export else None,
        }

    def _decode_state(self, value: dict[str, object]) -> _State:
        installation_id = str(value["installation_id"])
        period_start = datetime.fromisoformat(str(value["period_start"]))
        counters = {TelemetryMetric(name): int(count) for name, count in dict(value.get("counters", {})).items()}
        distributions = {name: self._decode_histogram(dict(raw)) for name, raw in dict(value.get("distributions", {})).items() if name in _PERFORMANCE_DISTRIBUTIONS}
        pending = [self._decode_pending(dict(raw)) for raw in list(value.get("pending", []))]
        successful = value.get("last_successful_export")
        state = _State(installation_id, str(value.get("ai_governance_version", __version__)), period_start, counters, distributions, pending, value.get("last_export_status") if isinstance(value.get("last_export_status"), str) else None, datetime.fromisoformat(str(successful)) if successful else None)
        if state.ai_governance_version != __version__:
            state.counters[TelemetryMetric.INSTALLATION_UPGRADED] = state.counters.get(TelemetryMetric.INSTALLATION_UPGRADED, 0) + 1
            state.ai_governance_version = __version__
        return state

    @staticmethod
    def _decode_histogram(raw: dict[str, object]) -> DurationHistogram:
        return DurationHistogram(
            count=int(raw["count"]), minimum_ms=int(raw["min_ms"]) if raw["count"] else None,
            maximum_ms=int(raw["max_ms"]) if raw["count"] else None,
            le_10ms=int(raw["le_10ms"]), le_100ms=int(raw["le_100ms"]), le_1s=int(raw["le_1s"]),
            le_10s=int(raw["le_10s"]), le_60s=int(raw["le_60s"]), gt_60s=int(raw["gt_60s"]),
        )

    def _decode_pending(self, raw: dict[str, object]) -> tuple[TelemetrySnapshot, int]:
        payload = dict(raw["payload"])
        guard = TelemetryPrivacyGuard()
        guard.validate_payload(payload)
        snapshot = TelemetrySnapshot(
            installation_id=str(payload["installation_id"]), ai_governance_version=str(payload["ai_governance_version"]),
            period_start=datetime.fromisoformat(str(payload["period_start"])), period_end=datetime.fromisoformat(str(payload["period_end"])),
            category=TelemetryCategory(str(payload["category"])),
            metrics=tuple((TelemetryMetric(name), int(count)) for name, count in dict(payload["metrics"]).items()),
            distributions=tuple((name, self._decode_histogram(dict(raw_histogram))) for name, raw_histogram in dict(payload["distributions"]).items()),
        )
        return snapshot, int(raw["attempts"])

    def _configured_exporter(self) -> TelemetryExporter:
        if self._exporter_type() != "posthog":
            return NoneTelemetryExporter()
        try:
            reference = str(self._configuration.get("telemetry.exporter.posthog_api_key_ref"))
            api_key = EnvironmentSecretReferenceResolver().resolve(reference)
            return PostHogTelemetryExporter(api_key, str(self._configuration.get("telemetry.exporter.posthog_endpoint")))
        except Exception:  # noqa: BLE001 - missing exporter credentials disable optional telemetry.
            return NoneTelemetryExporter()

    def _exporter_type(self) -> str:
        try:
            return str(self._configuration.get("telemetry.exporter.type"))
        except Exception:  # noqa: BLE001 - telemetry is disabled when its configuration is unavailable.
            return "none"

    @staticmethod
    def _duration_name(metric: TelemetryMetric) -> str | None:
        return {
            TelemetryMetric.JOB_EXECUTIONS: "job_execution_duration",
            TelemetryMetric.EVALUATION_RUNS: "evaluation_duration",
            TelemetryMetric.REPLAY_RUNS: "replay_duration",
            TelemetryMetric.IMPACT_SIMULATIONS: "impact_simulation_duration",
        }.get(metric)


class TelemetryDeliveryWorker:
    """Low-priority worker that performs the only outbound telemetry work."""

    def __init__(self, service: TelemetryService, interval_seconds: float = 60.0) -> None:
        self._service, self._interval_seconds, self._stop = service, interval_seconds, Event()

    def run_forever(self) -> None:
        while not self._stop.is_set():
            self._service.flush()
            self._stop.wait(self._interval_seconds)

    def stop(self) -> None:
        self._stop.set()
