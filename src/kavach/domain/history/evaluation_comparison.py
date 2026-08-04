from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationMetricComparison:
    """
    Metric-level comparison between two evaluations.

    A missing baseline value means the metric is new in the candidate. A missing
    candidate value means the metric was removed from the candidate.
    """

    metric_name: str
    baseline_value: float | None
    candidate_value: float | None

    @property
    def score_difference(self) -> float | None:
        """
        Return candidate-minus-baseline when both values are available.
        """

        if self.baseline_value is None or self.candidate_value is None:
            return None

        return self.candidate_value - self.baseline_value


@dataclass(frozen=True)
class EvaluationComparison:
    """
    Governance comparison of two evaluations for the same execution.

    This is a structural comparison, not a policy decision. Drift severity is
    handled by DriftAnalyzer so callers can choose between raw comparison and
    governance drift depending on the workflow.
    """

    execution_id: str
    baseline_evaluation_id: str
    candidate_evaluation_id: str
    metric_comparisons: list[EvaluationMetricComparison]
