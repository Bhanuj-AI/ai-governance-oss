from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import get_evaluation_repository
from ai_governance.domain.evaluation_result import EvaluationMetric, EvaluationResult
from ai_governance.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)


def _client() -> tuple[TestClient, InMemoryEvaluationRepository]:
    repository = InMemoryEvaluationRepository()
    repository.save(
        EvaluationResult(
            evaluation_id="eval-1",
            execution_id="exec-1",
            evaluator_type="fake",
            evaluator_version="1.0.0",
            metrics=[
                EvaluationMetric("answer_relevance", 0.8),
                EvaluationMetric("groundedness", 0.6),
            ],
            created_at=datetime(2026, 6, 27, tzinfo=UTC),
        )
    )
    repository.save(
        EvaluationResult(
            evaluation_id="eval-2",
            execution_id="exec-1",
            evaluator_type="fake",
            evaluator_version="1.0.0",
            metrics=[
                EvaluationMetric("answer_relevance", 0.9),
                EvaluationMetric("groundedness", 0.9),
            ],
            created_at=datetime(2026, 6, 27, 0, 0, 1, tzinfo=UTC),
        )
    )
    app = create_app()
    app.dependency_overrides[get_evaluation_repository] = lambda: repository
    return TestClient(app), repository


def test_compare_evaluations() -> None:
    client, _repository = _client()

    response = client.post(
        "/api/v1/governance/compare",
        json={
            "baseline_evaluation_id": "eval-1",
            "candidate_evaluation_id": "eval-2",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_id"] == "exec-1"
    assert payload["metric_comparisons"][0]["metric_name"] == (
        "answer_relevance"
    )


def test_analyze_drift() -> None:
    client, _repository = _client()

    response = client.post(
        "/api/v1/governance/drift",
        json={
            "baseline_evaluation_id": "eval-1",
            "candidate_evaluation_id": "eval-2",
        },
    )

    assert response.status_code == 200
    assert response.json()["severity"] == "HIGH"
    assert response.json()["changed_metrics"]


def test_governance_report_returns_501_when_not_supported() -> None:
    client, _repository = _client()

    response = client.get("/api/v1/governance/reports/eval-1")

    assert response.status_code == 501
    assert response.json()["error"]["code"] == (
        "GOVERNANCE_REPORT_NOT_IMPLEMENTED"
    )


def test_missing_evaluation_returns_404() -> None:
    client, _repository = _client()

    response = client.post(
        "/api/v1/governance/compare",
        json={
            "baseline_evaluation_id": "missing",
            "candidate_evaluation_id": "eval-2",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVALUATION_NOT_FOUND"


def test_malformed_governance_request_returns_422() -> None:
    client, _repository = _client()

    response = client.post(
        "/api/v1/governance/compare",
        json={"baseline_evaluation_id": "eval-1"},
    )

    assert response.status_code == 422


def test_mismatched_evaluation_executions_return_400() -> None:
    client, repository = _client()
    repository.save(
        EvaluationResult(
            evaluation_id="eval-other",
            execution_id="exec-2",
            evaluator_type="fake",
            evaluator_version="1.0.0",
            metrics=[EvaluationMetric("answer_relevance", 0.5)],
        )
    )

    response = client.post(
        "/api/v1/governance/compare",
        json={
            "baseline_evaluation_id": "eval-1",
            "candidate_evaluation_id": "eval-other",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_GOVERNANCE_REQUEST"


def test_governance_endpoints_are_in_openapi() -> None:
    client, _repository = _client()

    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/governance/compare" in paths
    assert "/api/v1/governance/drift" in paths
    assert "/api/v1/governance/reports/{evaluation_id}" in paths


def test_governance_router_has_no_repository_or_provider_adapter_imports() -> None:
    source = Path("src/ai_governance/api/routers/governance.py").read_text()

    assert "ai_governance.repositories" not in source
    assert "Repository" not in source
    assert "ai_governance.providers.trulens" not in source
    assert "import trulens" not in source
    assert "import openai" not in source
