import pytest

from kavach.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationResult,
)
from kavach.governance import (
    DriftAnalyzer,
    DriftSeverity,
)


def test_drift_analyzer_detects_changed_new_and_removed_metrics() -> None:
    baseline = EvaluationResult(
        evaluation_id="baseline",
        execution_id="execution-1",
        evaluator_type="FAKE",
        evaluator_version="1.0",
        metrics=[
            EvaluationMetric(
                metric_name="ANSWER_RELEVANCE",
                metric_value=0.8,
            ),
            EvaluationMetric(
                metric_name="CONTEXT_RELEVANCE",
                metric_value=0.6,
            ),
        ],
        metadata={},
    )
    candidate = EvaluationResult(
        evaluation_id="candidate",
        execution_id="execution-1",
        evaluator_type="FAKE",
        evaluator_version="1.0",
        metrics=[
            EvaluationMetric(
                metric_name="ANSWER_RELEVANCE",
                metric_value=0.9,
            ),
            EvaluationMetric(
                metric_name="GROUNDEDNESS",
                metric_value=0.7,
            ),
        ],
        metadata={},
    )

    drift = DriftAnalyzer().analyze(
        baseline=baseline,
        candidate=candidate,
    )

    assert drift.baseline_evaluation_id == "baseline"
    assert drift.candidate_evaluation_id == "candidate"
    assert drift.score_difference == pytest.approx(0.1)
    assert drift.severity == DriftSeverity.MEDIUM
    assert [metric.metric_name for metric in drift.changed_metrics] == [
        "ANSWER_RELEVANCE",
    ]
    assert drift.changed_metrics[0].score_difference == pytest.approx(0.1)
    assert [metric.metric_name for metric in drift.new_metrics] == [
        "GROUNDEDNESS",
    ]
    assert drift.new_metrics[0].baseline_value is None
    assert drift.new_metrics[0].candidate_value == 0.7
    assert [metric.metric_name for metric in drift.removed_metrics] == [
        "CONTEXT_RELEVANCE",
    ]
    assert drift.removed_metrics[0].baseline_value == 0.6
    assert drift.removed_metrics[0].candidate_value is None


def test_drift_analyzer_returns_none_severity_when_results_match() -> None:
    baseline = EvaluationResult(
        evaluation_id="baseline",
        execution_id="execution-1",
        evaluator_type="FAKE",
        evaluator_version="1.0",
        metrics=[
            EvaluationMetric(
                metric_name="ANSWER_RELEVANCE",
                metric_value=0.8,
            ),
        ],
        metadata={},
    )
    candidate = EvaluationResult(
        evaluation_id="candidate",
        execution_id="execution-1",
        evaluator_type="FAKE",
        evaluator_version="1.0",
        metrics=[
            EvaluationMetric(
                metric_name="ANSWER_RELEVANCE",
                metric_value=0.8,
            ),
        ],
        metadata={},
    )

    drift = DriftAnalyzer().analyze(
        baseline=baseline,
        candidate=candidate,
    )

    assert drift.score_difference == 0.0
    assert drift.changed_metrics == []
    assert drift.new_metrics == []
    assert drift.removed_metrics == []
    assert drift.severity == DriftSeverity.NONE


def test_drift_analyzer_escalates_large_score_changes() -> None:
    baseline = EvaluationResult(
        evaluation_id="baseline",
        execution_id="execution-1",
        evaluator_type="FAKE",
        evaluator_version="1.0",
        metrics=[
            EvaluationMetric(
                metric_name="ANSWER_RELEVANCE",
                metric_value=0.95,
            ),
        ],
        metadata={},
    )
    candidate = EvaluationResult(
        evaluation_id="candidate",
        execution_id="execution-1",
        evaluator_type="FAKE",
        evaluator_version="1.0",
        metrics=[
            EvaluationMetric(
                metric_name="ANSWER_RELEVANCE",
                metric_value=0.65,
            ),
        ],
        metadata={},
    )

    drift = DriftAnalyzer().analyze(
        baseline=baseline,
        candidate=candidate,
    )

    assert drift.score_difference == pytest.approx(-0.3)
    assert drift.severity == DriftSeverity.HIGH
