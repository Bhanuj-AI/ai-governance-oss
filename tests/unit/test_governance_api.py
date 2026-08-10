import pytest

from ai_governance.api import GovernanceAPI
from ai_governance.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from ai_governance.services.history import EvaluationHistoryService


def test_governance_api_exposes_phase_5_get_routes() -> None:
    api = GovernanceAPI(
        EvaluationHistoryService(
            InMemoryEvaluationRepository()
        )
    )

    routes = api.routes()

    assert [
        (route.method, route.path, route.handler_name)
        for route in routes
    ] == [
        ("GET", "/history/{execution}", "get_history"),
        ("GET", "/history/{execution}/latest", "get_latest"),
        ("GET", "/history/{execution}/drift", "get_drift"),
        ("GET", "/history/{execution}/compare", "get_compare"),
    ]


def test_governance_api_returns_history_payload() -> None:
    api = _create_api()

    payload = api.get_history("execution-1")

    assert payload["execution_id"] == "execution-1"
    assert payload["records"][0]["evaluation_id"] == "evaluation-1"
    assert payload["records"][1]["evaluation_id"] == "evaluation-2"


def test_governance_api_returns_latest_payload() -> None:
    api = _create_api()

    payload = api.get_latest("execution-1")

    assert payload is not None
    assert payload["evaluation_id"] == "evaluation-2"
    assert payload["metrics"][0]["metric_value"] == 0.65


def test_governance_api_returns_none_latest_payload() -> None:
    api = GovernanceAPI(
        EvaluationHistoryService(
            InMemoryEvaluationRepository()
        )
    )

    assert api.get_latest("missing-execution") is None


def test_governance_api_returns_drift_payload() -> None:
    api = _create_api()

    payload = api.get_drift(
        execution="execution-1",
        baseline_evaluation_id="evaluation-1",
        candidate_evaluation_id="evaluation-2",
    )

    assert payload["score_difference"] == pytest.approx(-0.3)
    assert payload["severity"] == "HIGH"
    assert payload["changed_metrics"][0]["metric_name"] == "ANSWER_RELEVANCE"


def test_governance_api_returns_compare_payload() -> None:
    api = _create_api()

    payload = api.get_compare(
        execution="execution-1",
        baseline_evaluation_id="evaluation-1",
        candidate_evaluation_id="evaluation-2",
    )

    assert payload["execution_id"] == "execution-1"
    assert payload["baseline_evaluation_id"] == "evaluation-1"
    assert payload["candidate_evaluation_id"] == "evaluation-2"
    assert payload["metric_comparisons"][0]["metric_name"] == (
        "ANSWER_RELEVANCE"
    )
    assert payload["metric_comparisons"][0]["score_difference"] == (
        pytest.approx(-0.3)
    )


def _create_api() -> GovernanceAPI:
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

    return GovernanceAPI(
        EvaluationHistoryService(repository)
    )
