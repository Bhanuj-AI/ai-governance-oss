from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class ReplayComparisonSummary:
    metric_count: int
    improved_metric_count: int
    regressed_metric_count: int
    unchanged_metric_count: int
    new_metric_count: int
    removed_metric_count: int
    overall_score_delta: float | None


@dataclass(frozen=True)
class ReplayDriftSummary:
    severity: str
    changed_metrics: tuple[str, ...]
    new_metrics: tuple[str, ...]
    removed_metrics: tuple[str, ...]
    analyzer_version: str
    threshold_policy: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "threshold_policy", MappingProxyType(dict(self.threshold_policy)))


@dataclass(frozen=True)
class ReplayResult:
    """Immutable governed evidence produced by a completed Replay."""

    result_id: str
    replay_id: str
    source_execution_id: str
    replay_execution_id: str
    baseline_evaluation_id: str
    replay_evaluation_id: str
    comparison_id: str
    drift_id: str
    baseline_strategy: str
    comparison_summary: ReplayComparisonSummary
    drift_summary: ReplayDriftSummary
    organization_id: str
    project_id: str
    created_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "result_id", "replay_id", "source_execution_id", "replay_execution_id",
            "baseline_evaluation_id", "replay_evaluation_id", "comparison_id",
            "drift_id", "baseline_strategy", "organization_id", "project_id",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"Replay result {name} is required.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
