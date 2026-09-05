from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies.settings_control import (
    get_configuration_service,
    get_settings_repository,
)
from ai_governance.settings_control.repository import InMemorySettingsRepository
from ai_governance.settings_control.service import ConfigurationService


def _client() -> tuple[TestClient, InMemorySettingsRepository]:
    repository = InMemorySettingsRepository()
    service = ConfigurationService(repository, {})
    app = create_app()
    app.dependency_overrides[get_settings_repository] = lambda: repository
    app.dependency_overrides[get_configuration_service] = lambda: service
    return TestClient(app), repository


def test_settings_api_lists_categories_and_effective_metadata() -> None:
    client, _ = _client()
    response = client.get("/api/v1/settings", params={"category": "Jobs"})

    assert response.status_code == 200
    assert response.json()
    assert {item["category"] for item in response.json()} == {"Jobs"}
    assert all(
        {"source", "editable", "restart_required", "default"} <= set(item)
        for item in response.json()
    )
    categories_response = client.get("/api/v1/settings/categories")
    assert categories_response.status_code == 200
    categories = categories_response.json()
    assert any(
        item["name"] == "Agents Runtime" and item["setting_count"] > 0
        for item in categories
    )

    runtime_settings = client.get(
        "/api/v1/settings", params={"category": "Agents Runtime"}
    )
    assert runtime_settings.status_code == 200
    assert runtime_settings.json()
    assert {item["category"] for item in runtime_settings.json()} == {
        "Agents Runtime"
    }


def test_settings_api_validates_updates_and_exposes_audit() -> None:
    client, _ = _client()
    headers = {
        "X-AI-Governance-Organization-Id": "org_default",
        "X-AI-Governance-Project-Id": "project_default",
        "X-AI-Governance-Actor-Id": "local-admin",
    }
    response = client.patch(
        "/api/v1/settings/mcp.dry_run_default",
        json={
            "value": True,
            "reason": "Safe project automation",
            "scope": "PROJECT",
            "expected_version": 0,
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["effective_value"] is True
    assert response.json()["source"] == "RUNTIME_PROJECT"
    assert (
        client.post(
            "/api/v1/settings/validate",
            json={"key": "jobs.retry_delay", "value": "soon"},
            headers=headers,
        ).status_code
        == 400
    )
    audit = client.get("/api/v1/settings/audit", headers=headers).json()
    assert audit[0]["actor_id"] == "local-admin"
    assert audit[0]["reason"] == "Safe project automation"

    stale = client.patch(
        "/api/v1/settings/mcp.dry_run_default",
        json={
            "value": False,
            "reason": "Stale write",
            "scope": "PROJECT",
            "expected_version": 0,
        },
        headers=headers,
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["current_version"] == 1


def test_settings_api_rejects_static_update() -> None:
    client, _ = _client()
    response = client.patch(
        "/api/v1/settings/system.version",
        json={"value": "99.0.0", "reason": "Attempt mutation", "expected_version": 0},
        headers={
            "X-AI-Governance-Organization-Id": "org_default",
            "X-AI-Governance-Project-Id": "project_default",
        },
    )
    assert response.status_code == 400
