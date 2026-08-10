from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.domain.history import EvaluationMetricComparison


class DriftSeverity(str, Enum):
    """
    Coarse governance severity assigned to evaluation drift.

    The values are intentionally simple so downstream API, CLI, and reporting
    layers can make policy decisions without understanding every metric-level
    detail.
    """

    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class EvaluationDrift:
    """
    Result of comparing a baseline evaluation against a candidate evaluation.

    This is the governance answer to "did quality move?" It groups metric
    changes into changed, new, and removed buckets, and provides a single
    severity signal for dashboards or review workflows.
    """

    baseline_evaluation_id: str
    candidate_evaluation_id: str
    score_difference: float | None
    changed_metrics: list[EvaluationMetricComparison]
    new_metrics: list[EvaluationMetricComparison]
    removed_metrics: list[EvaluationMetricComparison]
    severity: DriftSeverity


class DriftAnalyzer:
    """
    Compares two evaluation results and returns governance drift signals.

    The analyzer is deliberately independent from repositories and history
    services. Callers provide the two EvaluationResult objects they want to
    compare, and this class owns only the metric comparison and severity rules.
    """

    _MEDIUM_THRESHOLD = 0.10
    _HIGH_THRESHOLD = 0.20

    def analyze(
        self,
        baseline: EvaluationResult,
        candidate: EvaluationResult,
    ) -> EvaluationDrift:
        """
        Compare two evaluations and return metric-level drift.

        Metrics are matched by name. Shared metrics with different values are
        classified as changed, candidate-only metrics are new, and baseline-only
        metrics are removed. The overall score difference is the average delta
        across shared metrics.
        """

        baseline_metrics = self._metric_values_by_name(baseline)
        candidate_metrics = self._metric_values_by_name(candidate)

        common_metric_names = sorted(
            baseline_metrics.keys() & candidate_metrics.keys()
        )
        changed_metrics = [
            EvaluationMetricComparison(
                metric_name=metric_name,
                baseline_value=baseline_metrics[metric_name],
                candidate_value=candidate_metrics[metric_name],
            )
            for metric_name in common_metric_names
            if baseline_metrics[metric_name] != candidate_metrics[metric_name]
        ]
        new_metrics = [
            EvaluationMetricComparison(
                metric_name=metric_name,
                baseline_value=None,
                candidate_value=candidate_metrics[metric_name],
            )
            for metric_name in sorted(
                candidate_metrics.keys() - baseline_metrics.keys()
            )
        ]
        removed_metrics = [
            EvaluationMetricComparison(
                metric_name=metric_name,
                baseline_value=baseline_metrics[metric_name],
                candidate_value=None,
            )
            for metric_name in sorted(
                baseline_metrics.keys() - candidate_metrics.keys()
            )
        ]
        score_difference = self._average_score_difference(
            baseline_metrics,
            candidate_metrics,
            common_metric_names,
        )

        return EvaluationDrift(
            baseline_evaluation_id=baseline.evaluation_id,
            candidate_evaluation_id=candidate.evaluation_id,
            score_difference=score_difference,
            changed_metrics=changed_metrics,
            new_metrics=new_metrics,
            removed_metrics=removed_metrics,
            severity=self._severity(
                changed_metrics=changed_metrics,
                new_metrics=new_metrics,
                removed_metrics=removed_metrics,
            ),
        )

    @staticmethod
    def _metric_values_by_name(
        result: EvaluationResult,
    ) -> dict[str, float]:
        """
        Build a metric lookup for comparison logic.
        """

        return {
            metric.metric_name: metric.metric_value
            for metric in result.metrics
        }

    @staticmethod
    def _average_score_difference(
        baseline_metrics: dict[str, float],
        candidate_metrics: dict[str, float],
        metric_names: list[str],
    ) -> float | None:
        """
        Return the average candidate-minus-baseline score delta.

        A None result means the evaluations do not share any metrics, so an
        aggregate score movement would be misleading.
        """

        if not metric_names:
            return None

        return sum(
            candidate_metrics[metric_name] - baseline_metrics[metric_name]
            for metric_name in metric_names
        ) / len(metric_names)

    def _severity(
        self,
        changed_metrics: list[EvaluationMetricComparison],
        new_metrics: list[EvaluationMetricComparison],
        removed_metrics: list[EvaluationMetricComparison],
    ) -> DriftSeverity:
        """
        Assign severity from metric deltas and structural metric changes.

        Large score movement is high severity. New or removed metrics are at
        least medium severity because the evaluation surface itself changed.
        """

        if not changed_metrics and not new_metrics and not removed_metrics:
            return DriftSeverity.NONE

        max_score_delta = max(
            (
                abs(metric.score_difference)
                for metric in changed_metrics
                if metric.score_difference is not None
            ),
            default=0.0,
        )

        if max_score_delta >= self._HIGH_THRESHOLD:
            return DriftSeverity.HIGH

        if (
            max_score_delta >= self._MEDIUM_THRESHOLD
            or new_metrics
            or removed_metrics
        ):
            return DriftSeverity.MEDIUM

        return DriftSeverity.LOW
