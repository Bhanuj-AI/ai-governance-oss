"""Privacy-preserving, provider-neutral telemetry value objects.

The public snapshot schema intentionally contains only named aggregate fields.
It never carries a tenant, actor, request identifier, or customer-owned value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import re
from uuid import UUID


TELEMETRY_SCHEMA_VERSION = "1"
_VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}(?:[+.-][A-Za-z0-9.-]+)?$")


class TelemetryMode(str, Enum):
    STANDARD = "standard"
    DISABLED = "disabled"


class TelemetryCategory(str, Enum):
    ESSENTIAL = "ESSENTIAL"
    PRODUCT_ANALYTICS = "PRODUCT_ANALYTICS"
    PERFORMANCE_RESEARCH = "PERFORMANCE_RESEARCH"


class TelemetryMetric(str, Enum):
    INSTALLATION_STARTED = "installation_started"
    INSTALLATION_UPGRADED = "installation_upgraded"
    GOVERNED_EXECUTIONS = "governed_executions"
    EVALUATION_RUNS = "evaluation_runs"
    REPLAY_RUNS = "replay_runs"
    GOVERNANCE_DECISIONS = "governance_decisions"
    IMPACT_SIMULATIONS = "impact_simulations"
    BEHAVIOR_CONTRACTS_CREATED = "behavior_contracts_created"
    PROMPT_ASSETS = "prompt_assets"
    MODEL_ASSETS = "model_assets"
    DATASET_ASSETS = "dataset_assets"
    EVALUATION_PROVIDER_ASSETS = "evaluation_provider_assets"
    JOB_EXECUTIONS = "job_executions"


@dataclass(frozen=True)
class TelemetryPolicy:
    mode: TelemetryMode = TelemetryMode.STANDARD
    essential_enabled: bool = True
    product_analytics_enabled: bool = False
    performance_research_enabled: bool = False

    def allows(self, category: TelemetryCategory) -> bool:
        if self.mode is TelemetryMode.DISABLED:
            return False
        return {
            TelemetryCategory.ESSENTIAL: self.essential_enabled,
            TelemetryCategory.PRODUCT_ANALYTICS: self.product_analytics_enabled,
            TelemetryCategory.PERFORMANCE_RESEARCH: self.performance_research_enabled,
        }[category]


@dataclass(frozen=True)
class DurationHistogram:
    """A bounded latency distribution in milliseconds.

    Buckets are cumulative upper bounds: 10ms, 100ms, 1s, 10s, 60s, +Inf.
    """

    count: int = 0
    minimum_ms: int | None = None
    maximum_ms: int | None = None
    le_10ms: int = 0
    le_100ms: int = 0
    le_1s: int = 0
    le_10s: int = 0
    le_60s: int = 0
    gt_60s: int = 0

    def __post_init__(self) -> None:
        values = (
            self.count, self.le_10ms, self.le_100ms, self.le_1s,
            self.le_10s, self.le_60s, self.gt_60s,
        )
        if any(value < 0 for value in values):
            raise ValueError("Telemetry distribution values must be non-negative.")
        if sum(values[1:]) != self.count:
            raise ValueError("Telemetry histogram buckets must add up to count.")
        if self.count == 0 and (self.minimum_ms is not None or self.maximum_ms is not None):
            raise ValueError("An empty telemetry histogram cannot have bounds.")
        if self.count and (self.minimum_ms is None or self.maximum_ms is None):
            raise ValueError("A non-empty telemetry histogram requires bounds.")
        if self.minimum_ms is not None and self.maximum_ms is not None and self.minimum_ms > self.maximum_ms:
            raise ValueError("Telemetry histogram minimum cannot exceed maximum.")

    def observe(self, duration_ms: int) -> "DurationHistogram":
        if duration_ms < 0:
            raise ValueError("Telemetry duration must be non-negative.")
        bucket = (
            "le_10ms" if duration_ms <= 10 else "le_100ms" if duration_ms <= 100
            else "le_1s" if duration_ms <= 1_000 else "le_10s" if duration_ms <= 10_000
            else "le_60s" if duration_ms <= 60_000 else "gt_60s"
        )
        values = {name: getattr(self, name) for name in (
            "le_10ms", "le_100ms", "le_1s", "le_10s", "le_60s", "gt_60s"
        )}
        values[bucket] += 1
        return DurationHistogram(
            count=self.count + 1,
            minimum_ms=duration_ms if self.minimum_ms is None else min(self.minimum_ms, duration_ms),
            maximum_ms=duration_ms if self.maximum_ms is None else max(self.maximum_ms, duration_ms),
            **values,
        )

    def as_payload(self) -> dict[str, int]:
        return {
            "count": self.count,
            "min_ms": self.minimum_ms or 0,
            "max_ms": self.maximum_ms or 0,
            "le_10ms": self.le_10ms,
            "le_100ms": self.le_100ms,
            "le_1s": self.le_1s,
            "le_10s": self.le_10s,
            "le_60s": self.le_60s,
            "gt_60s": self.gt_60s,
        }


@dataclass(frozen=True)
class TelemetrySnapshot:
    """The versioned, allow-listed external telemetry envelope."""

    installation_id: str
    ai_governance_version: str
    period_start: datetime
    period_end: datetime
    category: TelemetryCategory
    metrics: tuple[tuple[TelemetryMetric, int], ...] = ()
    distributions: tuple[tuple[str, DurationHistogram], ...] = ()
    schema_version: str = TELEMETRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            UUID(self.installation_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("installation_id must be a UUID.") from exc
        if self.schema_version != TELEMETRY_SCHEMA_VERSION:
            raise ValueError("Unsupported telemetry schema version.")
        if not _VERSION_PATTERN.fullmatch(self.ai_governance_version):
            raise ValueError("ai_governance_version must be a release version, not arbitrary text.")
        if self.period_start.tzinfo is None or self.period_end.tzinfo is None:
            raise ValueError("Telemetry periods must be timezone-aware.")
        if self.period_end < self.period_start:
            raise ValueError("Telemetry period end cannot precede start.")
        metric_names = [metric.value for metric, _ in self.metrics]
        if len(metric_names) != len(set(metric_names)) or any(value < 0 for _, value in self.metrics):
            raise ValueError("Telemetry metrics must be unique non-negative counters.")
        names = [name for name, _ in self.distributions]
        if len(names) != len(set(names)) or any(not name.endswith("_duration") for name in names):
            raise ValueError("Telemetry distributions must be named duration aggregates.")

    def as_payload(self) -> dict[str, object]:
        """Return the only payload shape exporters are permitted to serialize."""
        metrics = {metric.value: value for metric, value in self.metrics}
        distributions = {name: histogram.as_payload() for name, histogram in self.distributions}
        return {
            "schema_version": self.schema_version,
            "installation_id": self.installation_id,
            "ai_governance_version": self.ai_governance_version,
            "period_start": self.period_start.astimezone(UTC).isoformat(),
            "period_end": self.period_end.astimezone(UTC).isoformat(),
            "category": self.category.value,
            "metrics": metrics,
            "distributions": distributions,
        }


@dataclass(frozen=True)
class TelemetryExportResult:
    delivered: bool
    retryable: bool = False
    status_code: int | None = None
    error_code: str | None = None
