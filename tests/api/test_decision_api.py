from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import get_governance_decision_repository
from ai_governance.repositories.in_memory import InMemoryGovernanceDecisionRepository


def _client() -> tuple[TestClient, InMemoryGovernanceDecisionRepository]:
    repository = InMemoryGovernanceDecisionRepository()
    app = create_app()
    app.dependency_overrides[get_governance_decision_repository] = (
        lambda: repository
    )
    return TestClient(app), repository


def _evaluate_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "target_type": "Candidate",
        "target_id": "candidate-1",
        "decision_type": "APPROVE",
        "policy_ids": [],
        "correlation_id": "corr-1",
        "request_id": "req-1",
        "metadata": {"source": "api-test"},
    }
    payload.update(overrides)
    return payload


def test_evaluate_persists_and_returns_decision_outcome() -> None:
    client, repository = _client()

    response = client.post(
        "/api/v1/decisions/evaluate",
        json=_evaluate_payload(),
    )

    assert response.status_code == 200
    payload = response.json()
    decision = payload["decision"]
    assert decision["target"] == {
        "target_type": "Candidate",
        "target_id": "candidate-1",
    }
    assert decision["provenance"]["request_id"] == "req-1"
    assert decision["metadata"] == {"source": "api-test"}
    assert payload["explanation"]["decision_id"] == decision["decision_id"]
    assert repository.get(decision["decision_id"]) is not None
    assert repository.find_audit_by_decision(decision["decision_id"])


def test_repeated_evaluate_with_same_request_id_is_idempotent() -> None:
    client, _repository = _client()

    first = client.post(
        "/api/v1/decisions/evaluate",
        json=_evaluate_payload(),
    )
    second = client.post(
        "/api/v1/decisions/evaluate",
        json=_evaluate_payload(),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert (
        second.json()["decision"]["decision_id"]
        == first.json()["decision"]["decision_id"]
    )


def test_reused_request_id_with_different_payload_returns_conflict() -> None:
    client, _repository = _client()
    client.post("/api/v1/decisions/evaluate", json=_evaluate_payload())

    response = client.post(
        "/api/v1/decisions/evaluate",
        json=_evaluate_payload(target_id="candidate-2"),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DecisionConflict"


def test_get_list_evidence_explanation_and_lineage_endpoints() -> None:
    client, _repository = _client()
    evaluated = client.post(
        "/api/v1/decisions/evaluate",
        json=_evaluate_payload(),
    ).json()
    decision_id = evaluated["decision"]["decision_id"]

    get_response = client.get(f"/api/v1/decisions/{decision_id}")
    detail_response = client.get(f"/api/v1/decisions/{decision_id}/detail")
    list_response = client.get(
        "/api/v1/decisions",
        params={"correlation_id": "corr-1"},
    )
    evidence_response = client.get(
        f"/api/v1/decisions/{decision_id}/evidence"
    )
    explanation_response = client.get(
        f"/api/v1/decisions/{decision_id}/explanation"
    )
    lineage_response = client.get(f"/api/v1/decisions/{decision_id}/lineage")

    assert get_response.status_code == 200
    assert get_response.json()["decision_id"] == decision_id
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["decision"]["decision_id"] == decision_id
    assert detail["evidence_summary"]["target_id"] == "candidate-1"
    assert detail["audit_records"][0]["action"] == "CREATED"
    assert list_response.status_code == 200
    assert list_response.json()["decisions"][0]["decision_id"] == decision_id
    assert evidence_response.status_code == 200
    assert evidence_response.json()["decision_id"] == decision_id
    assert explanation_response.status_code == 200
    assert explanation_response.json()["decision_id"] == decision_id
    assert lineage_response.status_code == 200
    assert lineage_response.json()["decision"]["decision_id"] == decision_id


def test_missing_decision_returns_structured_not_found() -> None:
    client, _repository = _client()

    response = client.get("/api/v1/decisions/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DecisionNotFound"


def test_decision_endpoints_are_in_openapi() -> None:
    client, _repository = _client()

    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/decisions/evaluate" in paths
    assert "/api/v1/decisions/{decision_id}" in paths
    assert "/api/v1/decisions/{decision_id}/detail" in paths
    assert "/api/v1/decisions/{decision_id}/evidence" in paths
    assert "/api/v1/decisions/{decision_id}/explanation" in paths
    assert "/api/v1/decisions/{decision_id}/lineage" in paths


def test_decision_router_has_no_repository_or_provider_adapter_imports() -> None:
    source = Path("src/ai_governance/api/routers/decisions.py").read_text()

    assert "ai_governance.repositories" not in source
    assert "Repository" not in source
    assert "ai_governance.providers.trulens" not in source
    assert "import trulens" not in source
    assert "import openai" not in source
