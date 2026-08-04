from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from kavach.api.app import create_app


def main() -> None:
    client = TestClient(create_app())

    health = _get(client, "/health")
    ready = _get(client, "/ready")
    metadata = _get(client, "/api/v1")
    providers = _get(client, "/api/v1/providers")

    baseline = _submit_evaluation(
        client,
        execution_id="rest-execution-1",
        answer="The claim appears valid.",
    )
    candidate = _submit_evaluation(
        client,
        execution_id="rest-execution-1",
        answer="The claim is valid with supporting evidence.",
    )
    comparison = _post(
        client,
        "/api/v1/governance/compare",
        {
            "baseline_evaluation_id": baseline["evaluation_id"],
            "candidate_evaluation_id": candidate["evaluation_id"],
        },
    )
    drift = _post(
        client,
        "/api/v1/governance/drift",
        {
            "baseline_evaluation_id": baseline["evaluation_id"],
            "candidate_evaluation_id": candidate["evaluation_id"],
        },
    )
    experiment = _post(
        client,
        "/api/v1/experiments",
        {
            "name": "rest-smoke-experiment",
            "description": "REST control-plane smoke experiment.",
            "metadata": {"owner": "smoke-test"},
        },
        expected_status=201,
    )
    job = _post(
        client,
        "/api/v1/jobs",
        {
            "job_type": "DRIFT_ANALYSIS",
            "input_refs": {
                "baseline_evaluation_id": baseline["evaluation_id"],
                "candidate_evaluation_id": candidate["evaluation_id"],
            },
            "idempotency_key": "rest-smoke-job-1",
            "submitted_by": "smoke-test",
            "max_attempts": 3,
        },
        expected_status=201,
    )
    jobs = _get(client, "/api/v1/jobs")
    cancelled = _post(client, f"/api/v1/jobs/{job['job_id']}/cancel", {})

    print("[health]")
    print(f"status={health['status']}")
    print(f"ready={ready['status']}")
    print(f"api_version={metadata['version']}")
    print()
    print("[providers]")
    print(f"providers={[provider['name'] for provider in providers]}")
    print()
    print("[evaluations]")
    print(f"baseline={baseline['evaluation_id']}")
    print(f"candidate={candidate['evaluation_id']}")
    print(f"latest_metric={candidate['metrics'][0]['name']}")
    print()
    print("[governance]")
    print(f"comparison_metrics={len(comparison['metric_comparisons'])}")
    print(f"drift_severity={drift['severity']}")
    print(f"drift_changed_metrics={drift['changed_metrics']}")
    print()
    print("[experiment]")
    print(f"experiment_id={experiment['experiment_id']}")
    print(f"status={experiment['status']}")
    print()
    print("[jobs]")
    print(f"submitted={job['job_id']}")
    print(f"listed={len(jobs['jobs'])}")
    print(f"cancelled_status={cancelled['status']}")


def _submit_evaluation(
    client: TestClient,
    *,
    execution_id: str,
    answer: str,
) -> dict[str, Any]:
    return _post(
        client,
        "/api/v1/evaluations",
        {
            "provider_name": "mock",
            "workflow_id": "rest-smoke-workflow",
            "workflow_name": "REST Smoke Workflow",
            "workflow_version": "1.0.0",
            "execution_id": execution_id,
            "execution_status": "COMPLETED",
            "input": {"question": "Was the claim valid?"},
            "final_state": {"answer": answer},
            "events": [{"event_type": "WORKFLOW_COMPLETED"}],
            "metric_specs": [{"name": "answer_relevance"}],
            "provider_config": {"api_key": "should-not-leak"},
        },
        expected_status=201,
    )


def _get(
    client: TestClient,
    path: str,
) -> dict[str, Any] | list[dict[str, Any]]:
    response = client.get(path)
    payload = response.json()
    _assert_http_status(response.status_code, 200, payload)
    return payload


def _post(
    client: TestClient,
    path: str,
    body: dict[str, Any],
    *,
    expected_status: int = 200,
) -> dict[str, Any]:
    response = client.post(path, json=body)
    payload = response.json()
    _assert_http_status(response.status_code, expected_status, payload)
    return payload


def _assert_http_status(
    actual: int,
    expected: int,
    payload: Any,
) -> None:
    if actual != expected:
        raise AssertionError(
            f"Expected HTTP {expected}, got {actual}: {payload}",
        )


if __name__ == "__main__":
    main()
