from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable
from uuid import uuid4

from kavach.domain.evaluation_result import EvaluationResult
from kavach.domain.history import EvaluationComparison, EvaluationMetricComparison
from kavach.domain.replay import (
    ReplayComparisonSummary,
    ReplayDriftSummary,
    ReplayResult,
)
from kavach.domain.replay.errors import (
    ReplayBaselineIncompatible,
    ReplayBaselineUnavailable,
    ReplayComparisonFailed,
)
from kavach.governance import DriftAnalyzer, EvaluationDrift
from kavach.services.evaluation_api_service import EvaluationApiService
from kavach.tenancy.domain import TenantContext


class BaselineStrategy:
    EXPLICIT = "EXPLICIT"
    LATEST_COMPATIBLE = "LATEST_COMPATIBLE"
    SOURCE_PRIMARY = "SOURCE_PRIMARY"


@dataclass(frozen=True)
class BaselineResolution:
    evaluation: EvaluationResult
    strategy: str
    compatibility_summary: dict[str, object]
    resolved_at: datetime


class ReplayBaselineResolver:
    """Resolves only tenant-scoped, evaluator-compatible source evidence."""

    def __init__(
        self,
        evaluations: EvaluationApiService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._evaluations = evaluations
        self._clock = clock or (lambda: datetime.now(UTC))

    def resolve(
        self,
        *,
        source_execution_id: str,
        replay_evaluation: EvaluationResult,
        strategy: str,
        explicit_evaluation_id: str | None,
        context: TenantContext,
    ) -> BaselineResolution:
        strategy = strategy.upper()
        if strategy not in {
            BaselineStrategy.EXPLICIT,
            BaselineStrategy.LATEST_COMPATIBLE,
            BaselineStrategy.SOURCE_PRIMARY,
        }:
            raise ReplayBaselineUnavailable(
                f"Unsupported replay baseline strategy '{strategy}'."
            )
        if strategy == BaselineStrategy.EXPLICIT:
            if not explicit_evaluation_id:
                raise ReplayBaselineUnavailable(
                    "An explicit baseline evaluation ID is required."
                )
            candidate = self._evaluations.get_evaluation(
                explicit_evaluation_id, context
            )
            if candidate.execution_id != source_execution_id:
                raise ReplayBaselineUnavailable(
                    "Explicit baseline does not belong to source execution."
                )
            self._ensure_compatible(candidate, replay_evaluation)
            return self._resolution(candidate, strategy, replay_evaluation)
        candidates = self._evaluations.get_history(source_execution_id, context)
        if strategy == BaselineStrategy.SOURCE_PRIMARY:
            primary = [
                item for item in candidates if item.metadata.get("primary") is True
            ]
            candidates = primary or candidates
        compatible = [
            item for item in candidates if self._compatible(item, replay_evaluation)
        ]
        if not compatible:
            raise ReplayBaselineUnavailable(
                "No compatible source evaluation is available."
            )
        selected = max(
            compatible, key=lambda item: (item.created_at, item.evaluation_id)
        )
        return self._resolution(selected, strategy, replay_evaluation)

    def _resolution(
        self, evaluation: EvaluationResult, strategy: str, replay: EvaluationResult
    ) -> BaselineResolution:
        return BaselineResolution(
            evaluation,
            strategy,
            {
                "evaluator_type": evaluation.evaluator_type,
                "evaluator_version": evaluation.evaluator_version,
                "shared_metrics": sorted(_metrics(evaluation) & _metrics(replay)),
            },
            self._clock(),
        )

    def _ensure_compatible(
        self, baseline: EvaluationResult, replay: EvaluationResult
    ) -> None:
        if not self._compatible(baseline, replay):
            raise ReplayBaselineIncompatible(
                "Baseline evaluator or metric schema is incompatible."
            )

    @staticmethod
    def _compatible(baseline: EvaluationResult, replay: EvaluationResult) -> bool:
        return (
            baseline.evaluator_type == replay.evaluator_type
            and baseline.evaluator_version == replay.evaluator_version
            and bool(_metrics(baseline) & _metrics(replay))
        )


class ReplayComparisonService:
    """Cross-execution comparison gated by immutable Replay lineage."""

    def compare(
        self,
        *,
        replay_id: str,
        source_execution_id: str,
        replay_execution_id: str,
        baseline: EvaluationResult,
        replay: EvaluationResult,
    ) -> EvaluationComparison:
        if (
            baseline.execution_id != source_execution_id
            or replay.execution_id != replay_execution_id
        ):
            raise ReplayComparisonFailed(
                "Evaluation executions do not match replay lineage."
            )
        names = sorted(_metrics(baseline) | _metrics(replay))
        return EvaluationComparison(
            execution_id=replay_execution_id,
            baseline_evaluation_id=baseline.evaluation_id,
            candidate_evaluation_id=replay.evaluation_id,
            metric_comparisons=[
                EvaluationMetricComparison(
                    name, _metric_value(baseline, name), _metric_value(replay, name)
                )
                for name in names
            ],
        )

    @staticmethod
    def summary(
        comparison: EvaluationComparison,
        baseline: EvaluationResult,
        replay: EvaluationResult,
    ) -> ReplayComparisonSummary:
        outcomes = [
            _outcome(item, baseline, replay) for item in comparison.metric_comparisons
        ]
        deltas = [
            item.score_difference
            for item in comparison.metric_comparisons
            if item.score_difference is not None
        ]
        return ReplayComparisonSummary(
            len(comparison.metric_comparisons),
            outcomes.count("IMPROVED"),
            outcomes.count("REGRESSED"),
            outcomes.count("UNCHANGED"),
            outcomes.count("NEW"),
            outcomes.count("REMOVED"),
            sum(deltas) / len(deltas) if deltas else None,
        )


class ReplayDriftService:
    analyzer_version = "governance-drift-v1"

    def __init__(self, analyzer: DriftAnalyzer | None = None) -> None:
        self._analyzer = analyzer or DriftAnalyzer()

    def analyze(
        self,
        baseline: EvaluationResult,
        replay: EvaluationResult,
        threshold_policy: dict[str, object],
    ) -> tuple[EvaluationDrift, ReplayDriftSummary]:
        drift = self._analyzer.analyze(baseline, replay)
        return drift, ReplayDriftSummary(
            drift.severity.value,
            tuple(item.metric_name for item in drift.changed_metrics),
            tuple(item.metric_name for item in drift.new_metrics),
            tuple(item.metric_name for item in drift.removed_metrics),
            self.analyzer_version,
            threshold_policy,
        )


def make_replay_result(
    *,
    replay,
    resolution: BaselineResolution,
    comparison_id: str,
    drift_id: str,
    comparison_summary: ReplayComparisonSummary,
    drift_summary: ReplayDriftSummary,
    result_id: str | None = None,
    now: datetime | None = None,
) -> ReplayResult:
    return ReplayResult(
        result_id or str(uuid4()),
        replay.replay_id,
        replay.source_execution_id,
        replay.replay_execution_id or "",
        replay.baseline_evaluation_id or "",
        replay.replay_evaluation_id or "",
        comparison_id,
        drift_id,
        resolution.strategy,
        comparison_summary,
        drift_summary,
        replay.organization_id,
        replay.project_id,
        now or datetime.now(UTC),
        {
            "baseline_compatibility": resolution.compatibility_summary,
            "threshold_policy": dict(drift_summary.threshold_policy),
        },
    )


def _metrics(result: EvaluationResult) -> set[str]:
    return {metric.metric_name for metric in result.metrics}


def _metric_value(result: EvaluationResult, name: str) -> float | None:
    return next(
        (
            metric.metric_value
            for metric in result.metrics
            if metric.metric_name == name
        ),
        None,
    )


def _outcome(
    comparison: EvaluationMetricComparison,
    baseline: EvaluationResult,
    replay: EvaluationResult,
) -> str:
    if comparison.baseline_value is None:
        return "NEW"
    if comparison.candidate_value is None:
        return "REMOVED"
    if comparison.score_difference == 0:
        return "UNCHANGED"
    direction = replay.metadata.get("metric_directions", {}).get(
        comparison.metric_name
    ) or baseline.metadata.get("metric_directions", {}).get(comparison.metric_name)
    if direction not in {"HIGHER_IS_BETTER", "LOWER_IS_BETTER"}:
        return "UNKNOWN"
    improved = (
        comparison.score_difference > 0
        if direction == "HIGHER_IS_BETTER"
        else comparison.score_difference < 0
    )
    return "IMPROVED" if improved else "REGRESSED"
