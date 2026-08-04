from __future__ import annotations

from kavach.api.models.governance import (
    DriftAnalysisResponse,
    EvaluationComparisonResponse,
    EvaluationMetricComparisonResponse,
)
from kavach.domain.history import (
    EvaluationComparison,
    EvaluationMetricComparison,
)
from kavach.governance import EvaluationDrift


class GovernanceApiMapper:
    """
    Converts governance domain objects into stable REST DTOs.
    """

    @staticmethod
    def to_comparison_response(
        comparison: EvaluationComparison,
    ) -> EvaluationComparisonResponse:
        """
        Convert an EvaluationComparison into a REST response.
        """
        return EvaluationComparisonResponse(
            execution_id=comparison.execution_id,
            baseline_evaluation_id=comparison.baseline_evaluation_id,
            candidate_evaluation_id=comparison.candidate_evaluation_id,
            metric_comparisons=[
                GovernanceApiMapper.to_metric_comparison_response(metric)
                for metric in comparison.metric_comparisons
            ],
        )

    @staticmethod
    def to_drift_response(
        drift: EvaluationDrift,
    ) -> DriftAnalysisResponse:
        """
        Convert EvaluationDrift into a REST response.
        """
        return DriftAnalysisResponse(
            baseline_evaluation_id=drift.baseline_evaluation_id,
            candidate_evaluation_id=drift.candidate_evaluation_id,
            score_difference=drift.score_difference,
            changed_metrics=[
                GovernanceApiMapper.to_metric_comparison_response(metric)
                for metric in drift.changed_metrics
            ],
            new_metrics=[
                GovernanceApiMapper.to_metric_comparison_response(metric)
                for metric in drift.new_metrics
            ],
            removed_metrics=[
                GovernanceApiMapper.to_metric_comparison_response(metric)
                for metric in drift.removed_metrics
            ],
            severity=drift.severity.value,
        )

    @staticmethod
    def to_metric_comparison_response(
        comparison: EvaluationMetricComparison,
    ) -> EvaluationMetricComparisonResponse:
        """
        Convert a metric comparison into a REST response.
        """
        return EvaluationMetricComparisonResponse(
            metric_name=comparison.metric_name,
            baseline_value=comparison.baseline_value,
            candidate_value=comparison.candidate_value,
            score_difference=comparison.score_difference,
        )
