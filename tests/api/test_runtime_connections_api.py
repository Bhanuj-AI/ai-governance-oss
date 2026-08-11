from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies.runtime_connections import get_runtime_connection_service
from ai_governance.repositories.settings_runtime_connection_repository import (
    SettingsRuntimeConnectionRepository,
)
from ai_governance.services.runtime_connection_service import RuntimeConnectionService
from ai_governance.settings_control.repository import InMemorySettingsRepository


class _SecretResolver:
    def resolve(self, reference: str) -> str:
        if reference == "env://AVAILABLE":
            return "resolved-secret"
        raise ValueError("unavailable")


def _client() -> TestClient:
    service = RuntimeConnectionService(
        SettingsRuntimeConnectionRepository(InMemorySettingsRepository()),
        secret_resolver=_SecretResolver(),
        allowed_runtime_providers=lambda _: ("openai", "custom"),
        id_generator=lambda: "connection-1",
        clock=lambda: datetime(2026, 8, 11, tzinfo=UTC),
    )
    app = create_app()
    app.dependency_overrides[get_runtime_connection_service] = lambda: service
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {
        "X-AI-Governance-Organization-Id": "org_default",
        "X-AI-Governance-Project-Id": "project_default",
        "X-AI-Governance-Actor-Id": "local-admin",
    }


def test_list_create_validate_and_test_runtime_connection() -> None:
    client = _client()

    providers = client.get("/api/v1/runtime-connections/providers", headers=_headers())
    validated = client.post(
        "/api/v1/runtime-connections/validate",
        headers=_headers(),
        json={
            "display_name": "OpenAI Development",
            "provider": "openai",
            "secret_refs": {"api_key": "env://AVAILABLE"},
        },
    )
    created = client.post(
        "/api/v1/runtime-connections",
        headers=_headers(),
        json={
            "display_name": "OpenAI Development",
            "provider": "openai",
            "settings": {"organization": "org_demo"},
            "secret_refs": {"api_key": "env://AVAILABLE"},
            "scope": "PROJECT",
        },
    )
    tested = client.post("/api/v1/runtime-connections/connection-1/test", headers=_headers())

    assert providers.status_code == 200
    assert {item["key"]: item["allowed"] for item in providers.json()} == {
        "openai": True,
        "anthropic": False,
        "custom": True,
    }
    assert validated.status_code == 200
    assert created.status_code == 201
    assert created.json()["scope"] == "PROJECT"
    assert created.json()["secret_refs"] == {"api_key": "env://AVAILABLE"}
    assert tested.status_code == 200
    assert tested.json()["last_test_status"] == "SUCCEEDED"


def test_runtime_connection_rejects_raw_secret_values_and_disallowed_providers() -> None:
    client = _client()

    raw_secret = client.post(
        "/api/v1/runtime-connections",
        headers=_headers(),
        json={
            "display_name": "Unsafe",
            "provider": "openai",
            "settings": {"api_key": "raw-secret"},
            "secret_refs": {"api_key": "env://AVAILABLE"},
        },
    )
    disallowed = client.post(
        "/api/v1/runtime-connections",
        headers=_headers(),
        json={
            "display_name": "Anthropic",
            "provider": "anthropic",
            "secret_refs": {"api_key": "env://AVAILABLE"},
        },
    )

    assert raw_secret.status_code == 400
    assert disallowed.status_code == 400
