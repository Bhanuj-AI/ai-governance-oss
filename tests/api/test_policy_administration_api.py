from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from kavach.api.app import create_app
from kavach.api.dependencies import get_policy_administration_repository
from kavach.repositories import InMemoryPolicyAdministrationRepository


def _client() -> tuple[TestClient, InMemoryPolicyAdministrationRepository]:
    store = InMemoryPolicyAdministrationRepository()
    app = create_app()
    app.dependency_overrides[get_policy_administration_repository] = (
        lambda: store
    )
    return TestClient(app), store


def _rule(
    expected_value: float = 0.8,
    effect: str = "APPROVE",
) -> dict[str, object]:
    return {
        "rule_id": "groundedness-gate",
        "name": "Groundedness gate",
        "conditions": [
            {
                "field_path": "metrics.groundedness.score",
                "operator": "GREATER_THAN",
                "expected_value": expected_value,
            }
        ],
        "effect": effect,
        "reason_template": "Groundedness passed.",
        "priority": 10,
        "severity": "HIGH",
        "metadata": {"owner": "risk"},
    }


def _policy_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Release gate",
        "description": "Approve grounded candidates.",
        "organization_id": "org-1",
        "project_id": "project-1",
        "category": "MODEL_RISK",
        "owner": "risk",
        "created_by": "admin",
        "target_types": ["Candidate"],
        "rules": [_rule()],
        "metadata": {"team": "studio"},
    }
    payload.update(overrides)
    return payload


def _create_policy(client: TestClient) -> dict[str, object]:
    response = client.post("/api/v1/policies", json=_policy_payload())
    assert response.status_code == 201
    return response.json()


def test_policy_schema_api_returns_authoring_metadata() -> None:
    client, _store = _client()

    response = client.get("/api/v1/policy-schema")

    assert response.status_code == 200
    payload = response.json()
    assert "Candidate" in [
        target_type["value"] for target_type in payload["target_types"]
    ]
    assert "MODEL_RISK" in payload["categories"]
    assert "GREATER_THAN" in payload["operators"]
    assert "HIGH" in payload["severities"]


def test_create_list_get_activate_archive_and_simulate_policy() -> None:
    client, _store = _client()
    created = _create_policy(client)
    policy_id = created["policy_id"]

    list_response = client.get(
        "/api/v1/policies",
        params={"project_id": "project-1"},
    )
    get_response = client.get(f"/api/v1/policies/{policy_id}")
    version_get_response = client.get(
        f"/api/v1/policies/{policy_id}/versions/1"
    )
    activate_response = client.post(
        f"/api/v1/policies/{policy_id}/versions/1/activate",
        json={"activated_by": "admin"},
    )
    version_response = client.post(
        f"/api/v1/policies/{policy_id}/versions",
        json={
            "base_version": "1",
            "target_types": ["Candidate"],
            "rules": [_rule(expected_value=0.9)],
            "created_by": "admin",
            "metadata": {"change": "raise-threshold"},
        },
    )
    update_response = client.put(
        f"/api/v1/policies/{policy_id}/versions/2/draft",
        json={
            "target_types": ["Candidate"],
            "rules": [_rule(expected_value=0.92)],
            "updated_by": "admin",
            "metadata": {"change": "tighten"},
        },
    )
    simulate_response = client.post(
        f"/api/v1/policies/{policy_id}/versions/2/simulate",
        json={
            "target_type": "Candidate",
            "target_id": "candidate-1",
            "evidence": {"metrics": {"groundedness": {"score": 0.93}}},
            "metadata": {"request_id": "sim-1"},
        },
    )
    archive_response = client.post(
        f"/api/v1/policies/{policy_id}/versions/2/archive",
        json={"archived_by": "admin"},
    )

    assert list_response.status_code == 200
    assert list_response.json()[0]["policy_id"] == policy_id
    assert get_response.status_code == 200
    assert version_get_response.status_code == 200
    assert version_get_response.json()["rules"][0]["rule_id"] == (
        "groundedness-gate"
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["active_version"]["version"] == "1"
    assert version_response.status_code == 201
    assert version_response.json()["draft_version"]["version"] == "2"
    assert update_response.status_code == 200
    assert update_response.json()["draft_version"]["rules"][0][
        "severity"
    ] == "HIGH"
    assert simulate_response.status_code == 200
    simulated = simulate_response.json()
    assert simulated["matched"] is True
    assert simulated["evaluation_trace"][0]["actual_value"] == 0.93
    assert archive_response.status_code == 200
    assert archive_response.json()["draft_version"] is None


def test_list_policies_supports_search_filters_and_pagination() -> None:
    client, _store = _client()
    for index in range(12):
        response = client.post(
            "/api/v1/policies",
            json=_policy_payload(
                name=f"Release gate {index:02d}",
                project_id="project-a" if index % 2 == 0 else "project-b",
                owner="risk" if index % 2 == 0 else "platform",
                rules=[
                    _rule(
                        effect="APPROVE" if index % 2 == 0 else "REJECT",
                    )
                ],
            ),
        )
        assert response.status_code == 201

    page_response = client.get(
        "/api/v1/policies",
        params={"limit": 10, "offset": 0},
    )
    next_page_response = client.get(
        "/api/v1/policies",
        params={"limit": 10, "offset": 10},
    )
    filtered_response = client.get(
        "/api/v1/policies",
        params={
            "search": "release gate 03",
            "project_id": "project-b",
            "owner": "platform",
            "effect": "REJECT",
            "limit": 10,
        },
    )

    assert page_response.status_code == 200
    assert len(page_response.json()) == 10
    assert next_page_response.status_code == 200
    assert len(next_page_response.json()) == 2
    assert filtered_response.status_code == 200
    assert [item["name"] for item in filtered_response.json()] == [
        "Release gate 03"
    ]


def test_update_active_policy_returns_structured_error() -> None:
    client, _store = _client()
    policy_id = _create_policy(client)["policy_id"]
    client.post(
        f"/api/v1/policies/{policy_id}/versions/1/activate",
        json={"activated_by": "admin"},
    )

    response = client.put(
        f"/api/v1/policies/{policy_id}/versions/1/draft",
        json={
            "target_types": ["Candidate"],
            "rules": [_rule(expected_value=0.9)],
            "updated_by": "admin",
            "metadata": {},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "InvalidPolicyRequest"


def test_missing_policy_returns_structured_error() -> None:
    client, _store = _client()

    response = client.get("/api/v1/policies/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PolicyNotFound"


def test_policy_admin_endpoints_are_in_openapi() -> None:
    client, _store = _client()

    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/policy-schema" in paths
    assert "/api/v1/policies" in paths
    assert "/api/v1/policies/{policy_id}" in paths
    assert "/api/v1/policies/{policy_id}/versions" in paths
    assert "/api/v1/policies/{policy_id}/versions/{version}" in paths
    assert "/api/v1/policies/{policy_id}/versions/{version}/draft" in paths
    assert (
        "/api/v1/policies/{policy_id}/versions/{version}/activate"
        in paths
    )
    assert (
        "/api/v1/policies/{policy_id}/versions/{version}/archive"
        in paths
    )
    assert (
        "/api/v1/policies/{policy_id}/versions/{version}/simulate"
        in paths
    )


def test_policy_router_has_no_storage_imports() -> None:
    source = Path("src/kavach/api/routers/policies.py").read_text()

    assert "kavach.repositories" not in source
    assert "Repository" not in source
