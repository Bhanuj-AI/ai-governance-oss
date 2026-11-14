from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ai_governance.settings_control.domain import SettingContext
from ai_governance.tenancy.domain import TenantContext

_DURATION_FACTORS = {
    "ms": 0.001,
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def duration_seconds(value: str) -> float:
    normalized = value.strip().lower()
    for unit, factor in _DURATION_FACTORS.items():
        if not normalized.endswith(unit):
            continue
        amount = normalized[: -len(unit)]
        if amount and amount[0] != "0" and amount.isascii() and amount.isdecimal():
            return int(amount) * factor
        break
    raise ValueError(f"Invalid duration: {value}")


def setting_context(context: TenantContext | None) -> SettingContext:
    return SettingContext(
        context.organization_id if context else None,
        context.project_id if context else None,
    )


@dataclass(frozen=True)
class EvaluationOutcome:
    passed: bool
    score: float
    threshold: float
    metric_thresholds: dict[str, float]
    failures: tuple[str, ...]


def evaluate_thresholds(
    metrics: Iterable[Any],
    default_threshold: float,
    configured_thresholds: dict[str, Any],
) -> EvaluationOutcome:
    scores = {str(item.metric_name): float(item.metric_value) for item in metrics}
    thresholds = {
        name: float(configured_thresholds.get(name, default_threshold))
        for name in scores
    }
    failures = tuple(name for name, score in scores.items() if score < thresholds[name])
    score = sum(scores.values()) / len(scores) if scores else 0.0
    return EvaluationOutcome(
        passed=bool(scores) and not failures,
        score=score,
        threshold=default_threshold,
        metric_thresholds=thresholds,
        failures=failures,
    )
