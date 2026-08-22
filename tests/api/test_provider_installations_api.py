from __future__ import annotations

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies.provider_installations import (
    get_provider_installation_service,
)
from ai_governance.providers import EvaluationProviderRegistry, MockEvaluationProvider
from ai_governance.repositories.settings_provider_installation_repository import (
    SettingsProviderInstallationRepository,
)
from ai_governance.services.provider_installation_service import (
    ProviderInstallationService,
)
from ai_governance.settings_control.repository import InMemorySettingsRepository


def _client() -> TestClient:
    registry = EvaluationProviderRegistry()
    registry.register(MockEvaluationProvider())
    service = ProviderInstallationService(
        SettingsProviderInstallationRepository(InMemorySettingsRepository()), registry
    )
    app = create_app()
    app.dependency_overrides[get_provider_installation_service] = lambda: service
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {
        "X-AI-Governance-Organization-Id": "org_default",
        "X-AI-Governance-Project-Id": "project_default",
        "X-AI-Governance-Actor-Id": "local-admin",
    }


def test_create_list_and_disable_provider_installation() -> None:
    client = _client()
    created = client.post(
        "/api/v1/provider-installations",
        headers=_headers(),
        json={
                "provider_type": "mock",
                "display_name": "Mock Production",
                "settings": {"mode": "deterministic"},
                "secret_refs": {},
            "enabled": True,
        },
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["provider_type"] == "mock"
    assert payload["adapter_version"] == "1.0.0"
    assert payload["scope"] == "ORGANIZATION"
    assert payload["secret_refs"] == {}
    assert client.get("/api/v1/provider-installations", headers=_headers()).json() == [payload]

    updated = client.patch(
        f"/api/v1/provider-installations/{payload['installation_id']}",
        headers=_headers(),
        json={"enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False


def test_validate_provider_installation_initializes_before_persisting() -> None:
    client = _client()

    response = client.post(
        "/api/v1/provider-installations/validate",
        headers=_headers(),
        json={
            "provider_type": "mock",
            "display_name": "Mock validation",
            "settings": {},
            "secret_refs": {},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "provider_type": "mock",
        "message": "Secret references resolved and provider initialization succeeded.",
    }
    assert client.get("/api/v1/provider-installations", headers=_headers()).json() == []


def test_provider_installation_rejects_unknown_type_and_secret_value() -> None:
    client = _client()
    unknown = client.post(
        "/api/v1/provider-installations",
        headers=_headers(),
        json={"provider_type": "missing", "display_name": "Missing"},
    )
    assert unknown.status_code == 400

    unsafe = client.post(
        "/api/v1/provider-installations",
        headers=_headers(),
        json={"provider_type": "mock", "display_name": "Unsafe", "settings": {"api_key": "value"}},
    )
    assert unsafe.status_code == 400
