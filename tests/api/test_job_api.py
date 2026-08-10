from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import get_job_repository
from ai_governance.domain.jobs import JobStatus
from ai_governance.repositories import InMemoryJobRepository


def _client() -> tuple[TestClient, InMemoryJobRepository]:
    repository = InMemoryJobRepository()
    app = create_app()
    app.dependency_overrides[get_job_repository] = lambda: repository
    return TestClient(app), repository


def _submit_payload(
    *,
    key: str = "job-key",
    job_type: str = "EVALUATION",
) -> dict[str, object]:
    return {
        "job_type": job_type,
        "input_refs": {
            "evaluation_id": "eval-1",
            "dataset_id": "dataset-1",
        },
        "idempotency_key": key,
        "submitted_by": "tester",
        "max_attempts": 3,
    }


def test_submit_job_returns_queued_job() -> None:
    client, _ = _client()

    response = client.post("/api/v1/jobs", json=_submit_payload())

    assert response.status_code == 201
    payload = response.json()
    assert payload["job_id"]
    assert payload["job_type"] == "EVALUATION"
    assert payload["status"] == "QUEUED"
    assert payload["input_refs"]["dataset_id"] == "dataset-1"
    assert payload["attempt_count"] == 0
    assert "leased_by" not in payload
    assert "heartbeat_at" not in payload


def test_submit_job_is_idempotent_for_same_input() -> None:
    client, _ = _client()

    first = client.post("/api/v1/jobs", json=_submit_payload())
    second = client.post("/api/v1/jobs", json=_submit_payload())

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["job_id"] == first.json()["job_id"]


def test_submit_job_conflict_for_same_key_different_input() -> None:
    client, _ = _client()
    first_payload = _submit_payload()
    second_payload = _submit_payload()
    second_payload["input_refs"] = {"evaluation_id": "different"}

    assert client.post("/api/v1/jobs", json=first_payload).status_code == 201
    response = client.post("/api/v1/jobs", json=second_payload)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_get_and_list_jobs_with_filters() -> None:
    client, repository = _client()
    evaluation = client.post(
        "/api/v1/jobs",
        json=_submit_payload(key="evaluation", job_type="EVALUATION"),
    ).json()
    drift = client.post(
        "/api/v1/jobs",
        json=_submit_payload(key="drift", job_type="DRIFT_ANALYSIS"),
    ).json()
    repository.mark_failed(drift["job_id"], "quality drift detected")

    get_response = client.get(f"/api/v1/jobs/{evaluation['job_id']}")
    list_response = client.get(
        "/api/v1/jobs",
        params={"status": "QUEUED", "job_type": "EVALUATION"},
    )

    assert get_response.status_code == 200
    assert get_response.json()["job_id"] == evaluation["job_id"]
    assert list_response.status_code == 200
    assert [job["job_id"] for job in list_response.json()["jobs"]] == [
        evaluation["job_id"]
    ]


def test_get_missing_job_returns_404() -> None:
    client, _ = _client()

    response = client.get("/api/v1/jobs/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_cancel_queued_job() -> None:
    client, _ = _client()
    job = client.post("/api/v1/jobs", json=_submit_payload()).json()

    response = client.post(f"/api/v1/jobs/{job['job_id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_terminal_job_returns_400() -> None:
    client, repository = _client()
    job = client.post("/api/v1/jobs", json=_submit_payload()).json()
    repository.mark_succeeded(job["job_id"], "result://job")

    response = client.post(f"/api/v1/jobs/{job['job_id']}/cancel")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_JOB_REQUEST"


def test_retry_failed_job_requeues_when_attempts_remain() -> None:
    client, repository = _client()
    job = client.post("/api/v1/jobs", json=_submit_payload()).json()
    repository.mark_failed(job["job_id"], "temporary failure")

    response = client.post(f"/api/v1/jobs/{job['job_id']}/retry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == job["job_id"]
    assert payload["status"] == "QUEUED"
    assert payload["failure_reason"] is None


def test_retry_exhausted_failed_job_creates_new_queued_job() -> None:
    client, repository = _client()
    job = client.post(
        "/api/v1/jobs",
        json=_submit_payload(key="exhausted"),
    ).json()
    stored = repository.find_by_id(job["job_id"])
    assert stored is not None
    repository.save(
        replace(
            stored,
            status=JobStatus.FAILED,
            attempt_count=stored.max_attempts,
            failure_reason="permanent failure",
        )
    )

    response = client.post(f"/api/v1/jobs/{job['job_id']}/retry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] != job["job_id"]
    assert payload["status"] == "QUEUED"
    assert payload["input_refs"] == job["input_refs"]


def test_retry_non_failed_job_returns_400() -> None:
    client, _ = _client()
    job = client.post("/api/v1/jobs", json=_submit_payload()).json()

    response = client.post(f"/api/v1/jobs/{job['job_id']}/retry")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_JOB_REQUEST"


def test_get_job_result_returns_status_and_result_ref() -> None:
    client, repository = _client()
    job = client.post("/api/v1/jobs", json=_submit_payload()).json()
    repository.mark_succeeded(job["job_id"], "result://evaluation/1")

    response = client.get(f"/api/v1/jobs/{job['job_id']}/result")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": job["job_id"],
        "status": "SUCCEEDED",
        "result_ref": "result://evaluation/1",
        "failure_reason": None,
    }


def test_job_resources_are_in_openapi() -> None:
    client, _ = _client()

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/jobs" in paths
    assert "/api/v1/jobs/{job_id}/cancel" in paths
    assert "/api/v1/jobs/{job_id}/retry" in paths
    assert "/api/v1/jobs/{job_id}/result" in paths
