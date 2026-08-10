from __future__ import annotations

from ai_governance.api.mappers import GovernanceApiMapper
from ai_governance.domain.history import (
    EvaluationComparison,
    EvaluationMetricComparison,
)
from ai_governance.governance import DriftSeverity, EvaluationDrift


def test_governance_comparison_mapper_includes_score_difference() -> None:
    comparison = EvaluationComparison(
        execution_id="exec-1",
        baseline_evaluation_id="eval-1",
        candidate_evaluation_id="eval-2",
        metric_comparisons=[
            EvaluationMetricComparison(
                metric_name="answer_relevance",
                baseline_value=0.8,
                candidate_value=0.9,
            )
        ],
    )

    response = GovernanceApiMapper.to_comparison_response(comparison)

    assert response.execution_id == "exec-1"
    assert response.metric_comparisons[0].score_difference == (
        0.09999999999999998
    )


def test_governance_drift_mapper_serializes_severity() -> None:
    drift = EvaluationDrift(
        baseline_evaluation_id="eval-1",
        candidate_evaluation_id="eval-2",
        score_difference=0.2,
        changed_metrics=[
            EvaluationMetricComparison(
                metric_name="groundedness",
                baseline_value=0.5,
                candidate_value=0.7,
            )
        ],
        new_metrics=[],
        removed_metrics=[],
        severity=DriftSeverity.HIGH,
    )

    response = GovernanceApiMapper.to_drift_response(drift)

    assert response.severity == "HIGH"
    assert response.changed_metrics[0].metric_name == "groundedness"
