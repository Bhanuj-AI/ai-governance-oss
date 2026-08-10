from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_governance.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.governance import DriftSeverity
from ai_governance.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from ai_governance.services.history import (
    EvaluationHistoryRecordNotFoundError,
    EvaluationHistoryService,
)
from ai_governance.tenancy.domain import TenantContext


def test_evaluation_history_service_returns_execution_history() -> None:
    repository = InMemoryEvaluationRepository()
    repository.save(
        EvaluationResult(
            evaluation_id="evaluation-1",
            execution_id="execution-1",
            evaluator_type="FAKE",
            evaluator_version="1.0",
            metrics=[
                EvaluationMetric(
                    metric_name="ANSWER_RELEVANCE",
                    metric_value=0.95,
                    explanation="Relevant",
                ),
            ],
            metadata={
                "judge_model": "fake-judge",
            },
        )
    )

    service = EvaluationHistoryService(repository)

    history = service.get_execution_history("execution-1")

    assert history.execution_id == "execution-1"
    assert history.evaluation_count == 1
    assert history.records[0].evaluation_id == "evaluation-1"
    assert history.records[0].evaluator_type == "FAKE"
    assert history.records[0].metadata == {"judge_model": "fake-judge"}
    assert history.records[0].metrics[0].metric_name == "ANSWER_RELEVANCE"
    assert history.records[0].metrics[0].metric_value == 0.95
    assert history.records[0].metrics[0].explanation == "Relevant"


def test_evaluation_history_service_returns_empty_history() -> None:
    service = EvaluationHistoryService(InMemoryEvaluationRepository())

    history = service.get_execution_history("missing-execution")

    assert history.execution_id == "missing-execution"
    assert history.evaluation_count == 0
    assert history.records == []


def test_evaluation_history_service_returns_latest_evaluation() -> None:
    repository = InMemoryEvaluationRepository()
    repository.save(
        EvaluationResult(
            evaluation_id="evaluation-1",
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
    )
    repository.save(
        EvaluationResult(
            evaluation_id="evaluation-2",
            execution_id="execution-1",
            evaluator_type="FAKE",
            evaluator_version="1.0",
            metrics=[
                EvaluationMetric(
                    metric_name="ANSWER_RELEVANCE",
                    metric_value=0.9,
                ),
            ],
            metadata={},
        )
    )

    service = EvaluationHistoryService(repository)

    latest = service.get_latest_evaluation("execution-1")

    assert latest is not None
    assert latest.evaluation_id == "evaluation-2"


def test_evaluation_history_service_returns_none_latest_evaluation() -> None:
    service = EvaluationHistoryService(InMemoryEvaluationRepository())

    latest = service.get_latest_evaluation("missing-execution")

    assert latest is None


def test_evaluation_history_service_orders_records_by_creation_then_id() -> None:
    repository = InMemoryEvaluationRepository()
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    repository.save(
        _result(
            evaluation_id="evaluation-b",
            created_at=created_at,
        )
    )
    repository.save(
        _result(
            evaluation_id="evaluation-a",
            created_at=created_at,
        )
    )
    repository.save(
        _result(
            evaluation_id="evaluation-c",
            created_at=created_at + timedelta(seconds=1),
        )
    )

    service = EvaluationHistoryService(repository)

    history = service.get_execution_history("execution-1")
    latest = service.get_latest_evaluation("execution-1")

    assert [record.evaluation_id for record in history.records] == [
        "evaluation-a",
        "evaluation-b",
        "evaluation-c",
    ]
    assert latest is not None
    assert latest.evaluation_id == "evaluation-c"


def test_evaluation_history_service_filters_history_to_tenant_context() -> None:
    repository = InMemoryEvaluationRepository()
    repository.save(
        _result(
            evaluation_id="included",
            organization_id="organization-1",
            project_id="project-1",
        )
    )
    repository.save(
        _result(
            evaluation_id="excluded",
            organization_id="organization-2",
            project_id="project-2",
        )
    )
    context = TenantContext(
        organization_id="organization-1",
        project_id="project-1",
        actor_id="actor-1",
        request_id="request-1",
    )

    history = EvaluationHistoryService(repository).get_execution_history(
        "execution-1", context
    )

    assert [record.evaluation_id for record in history.records] == ["included"]


def test_evaluation_history_service_returns_metric_history() -> None:
    repository = InMemoryEvaluationRepository()
    repository.save(
        EvaluationResult(
            evaluation_id="evaluation-1",
            execution_id="execution-1",
            evaluator_type="FAKE",
            evaluator_version="1.0",
            metrics=[
                EvaluationMetric(
                    metric_name="ANSWER_RELEVANCE",
                    metric_value=0.8,
                    explanation="First run",
                ),
            ],
            metadata={},
        )
    )
    repository.save(
        EvaluationResult(
            evaluation_id="evaluation-2",
            execution_id="execution-1",
            evaluator_type="FAKE",
            evaluator_version="1.0",
            metrics=[
                EvaluationMetric(
                    metric_name="ANSWER_RELEVANCE",
                    metric_value=0.9,
                    explanation="Second run",
                ),
                EvaluationMetric(
                    metric_name="GROUNDEDNESS",
                    metric_value=0.7,
                ),
            ],
            metadata={},
        )
    )

    service = EvaluationHistoryService(repository)

    trend = service.get_metric_history(
        execution_id="execution-1",
        metric_name="ANSWER_RELEVANCE",
    )

    assert trend.metric_name == "ANSWER_RELEVANCE"
    assert trend.evaluation_count == 2
    assert trend.average_metric_value == pytest.approx(0.85)
    assert trend.points[0].evaluation_id == "evaluation-1"
    assert trend.points[0].metric_value == 0.8
    assert trend.points[0].explanation == "First run"
    assert trend.points[1].evaluation_id == "evaluation-2"
    assert trend.points[1].metric_value == 0.9


def test_evaluation_history_service_returns_empty_metric_history() -> None:
    service = EvaluationHistoryService(InMemoryEvaluationRepository())

    trend = service.get_metric_history(
        execution_id="missing-execution",
        metric_name="ANSWER_RELEVANCE",
    )

    assert trend.metric_name == "ANSWER_RELEVANCE"
    assert trend.evaluation_count == 0
    assert trend.average_metric_value is None
    assert trend.points == []


def test_evaluation_history_service_returns_execution_summary() -> None:
    repository = InMemoryEvaluationRepository()
    repository.save(
        EvaluationResult(
            evaluation_id="evaluation-1",
            execution_id="execution-1",
            evaluator_type="FAKE",
            evaluator_version="1.0",
            metrics=[
                EvaluationMetric(
                    metric_name="ANSWER_RELEVANCE",
                    metric_value=0.8,
                ),
            ],
            metadata={
                "evaluated_at": "2026-06-25T10:00:00Z",
            },
        )
    )
    repository.save(
        EvaluationResult(
            evaluation_id="evaluation-2",
            execution_id="execution-1",
            evaluator_type="TRULENS",
            evaluator_version="2.8.1",
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
            metadata={
                "evaluated_at": "2026-06-25T11:00:00Z",
            },
        )
    )

    service = EvaluationHistoryService(repository)

    summary = service.get_execution_summary("execution-1")

    assert summary.execution_id == "execution-1"
    assert summary.latest_score == pytest.approx(0.8)
    assert summary.evaluation_count == 2
    assert summary.provider == "TRULENS"
    assert summary.provider_version == "2.8.1"
    assert summary.evaluated_at == "2026-06-25T11:00:00Z"


def test_evaluation_history_service_returns_empty_execution_summary() -> None:
    service = EvaluationHistoryService(InMemoryEvaluationRepository())

    summary = service.get_execution_summary("missing-execution")

    assert summary.execution_id == "missing-execution"
    assert summary.latest_score is None
    assert summary.evaluation_count == 0
    assert summary.provider is None
    assert summary.provider_version is None
    assert summary.evaluated_at is None


def test_evaluation_history_service_compares_evaluations() -> None:
    repository = InMemoryEvaluationRepository()
    repository.save(
        EvaluationResult(
            evaluation_id="evaluation-1",
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
    )
    repository.save(
        EvaluationResult(
            evaluation_id="evaluation-2",
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
    )

    service = EvaluationHistoryService(repository)

    comparison = service.compare_evaluations(
        execution_id="execution-1",
        baseline_evaluation_id="evaluation-1",
        candidate_evaluation_id="evaluation-2",
    )

    assert comparison.execution_id == "execution-1"
    assert comparison.baseline_evaluation_id == "evaluation-1"
    assert comparison.candidate_evaluation_id == "evaluation-2"
    assert [metric.metric_name for metric in comparison.metric_comparisons] == [
        "ANSWER_RELEVANCE",
        "CONTEXT_RELEVANCE",
        "GROUNDEDNESS",
    ]
    assert comparison.metric_comparisons[0].baseline_value == 0.8
    assert comparison.metric_comparisons[0].candidate_value == 0.9
    assert comparison.metric_comparisons[0].score_difference == pytest.approx(0.1)
    assert comparison.metric_comparisons[1].baseline_value == 0.6
    assert comparison.metric_comparisons[1].candidate_value is None
    assert comparison.metric_comparisons[1].score_difference is None
    assert comparison.metric_comparisons[2].baseline_value is None
    assert comparison.metric_comparisons[2].candidate_value == 0.7


@pytest.mark.parametrize(
    ("baseline_evaluation_id", "candidate_evaluation_id", "missing_evaluation_id"),
    [
        ("missing-baseline", "evaluation-1", "missing-baseline"),
        ("evaluation-1", "missing-candidate", "missing-candidate"),
    ],
)
def test_evaluation_history_service_rejects_missing_comparison_record(
    baseline_evaluation_id: str,
    candidate_evaluation_id: str,
    missing_evaluation_id: str,
) -> None:
    repository = InMemoryEvaluationRepository()
    repository.save(_result(evaluation_id="evaluation-1"))
    service = EvaluationHistoryService(repository)

    with pytest.raises(EvaluationHistoryRecordNotFoundError) as error:
        service.compare_evaluations(
            execution_id="execution-1",
            baseline_evaluation_id=baseline_evaluation_id,
            candidate_evaluation_id=candidate_evaluation_id,
        )

    assert error.value.execution_id == "execution-1"
    assert error.value.evaluation_id == missing_evaluation_id


def test_evaluation_history_service_rejects_missing_drift_record() -> None:
    repository = InMemoryEvaluationRepository()
    repository.save(_result(evaluation_id="evaluation-1"))
    service = EvaluationHistoryService(repository)

    with pytest.raises(EvaluationHistoryRecordNotFoundError) as error:
        service.analyze_drift(
            execution_id="execution-1",
            baseline_evaluation_id="evaluation-1",
            candidate_evaluation_id="missing-candidate",
        )

    assert error.value.execution_id == "execution-1"
    assert error.value.evaluation_id == "missing-candidate"


def test_evaluation_history_service_analyzes_drift() -> None:
    repository = InMemoryEvaluationRepository()
    repository.save(
        EvaluationResult(
            evaluation_id="evaluation-1",
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
    )
    repository.save(
        EvaluationResult(
            evaluation_id="evaluation-2",
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
    )

    service = EvaluationHistoryService(repository)

    drift = service.analyze_drift(
        execution_id="execution-1",
        baseline_evaluation_id="evaluation-1",
        candidate_evaluation_id="evaluation-2",
    )

    assert drift.score_difference == pytest.approx(-0.3)
    assert drift.severity == DriftSeverity.HIGH
    assert drift.changed_metrics[0].metric_name == "ANSWER_RELEVANCE"


def test_evaluation_history_service_uses_evaluation_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    repository = InMemoryEvaluationRepository()
    repository.save(
        _result(
            evaluation_id="older-than-cutoff",
            created_at=fixed_now - timedelta(hours=1, seconds=1),
        )
    )
    repository.save(
        _result(
            evaluation_id="at-cutoff",
            created_at=fixed_now - timedelta(hours=1),
        )
    )
    repository.save(
        _result(
            evaluation_id="newer-than-cutoff",
            created_at=fixed_now - timedelta(minutes=30),
        )
    )
    configuration = _RecordingConfigurationService()
    from ai_governance.services.history import evaluation_history_service

    monkeypatch.setattr(
        evaluation_history_service,
        "datetime",
        _FrozenDateTime.with_now(fixed_now),
    )

    history = EvaluationHistoryService(
        repository,
        configuration_service=configuration,
    ).get_execution_history("execution-1")

    assert [record.evaluation_id for record in history.records] == [
        "at-cutoff",
        "newer-than-cutoff",
    ]
    assert configuration.keys == ["evaluation.retention"]


def test_evaluation_history_service_returns_all_records_without_configuration() -> None:
    repository = InMemoryEvaluationRepository()
    repository.save(
        _result(
            evaluation_id="old-evaluation",
            created_at=datetime(2000, 1, 1, tzinfo=UTC),
        )
    )

    history = EvaluationHistoryService(repository).get_execution_history("execution-1")

    assert [record.evaluation_id for record in history.records] == ["old-evaluation"]


def test_evaluation_history_service_does_not_depend_on_replay_domain() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/ai_governance/services/history/evaluation_history_service.py"
    ).read_text()

    assert "ai_governance.domain.replay" not in source


class _RecordingConfigurationService:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def get(self, key: str, _context: object) -> str:
        self.keys.append(key)
        return "1h"


class _FrozenDateTime(datetime):
    _now: datetime

    @classmethod
    def with_now(cls, now: datetime) -> type["_FrozenDateTime"]:
        cls._now = now
        return cls

    @classmethod
    def now(cls, tz=None) -> datetime:
        return cls._now


def _result(
    evaluation_id: str,
    created_at: datetime | None = None,
    organization_id: str = "org_default",
    project_id: str = "project_default",
) -> EvaluationResult:
    return EvaluationResult(
        evaluation_id=evaluation_id,
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
        created_at=created_at or datetime.now(UTC),
        organization_id=organization_id,
        project_id=project_id,
    )
