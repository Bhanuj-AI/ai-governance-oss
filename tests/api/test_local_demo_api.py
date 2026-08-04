from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from kavach.api.app import create_app
from kavach.api.dependencies import get_api_settings


def test_local_demo_seed_is_idempotent() -> None:
    client = TestClient(create_app())

    first = client.post("/api/v1/local/demo/seed")
    second = client.post("/api/v1/local/demo/seed")

    assert first.status_code == 200
    assert first.json()["seeded"] is True
    assert first.json()["decision_ids"]
    assert second.status_code == 200
    assert second.json()["decision_ids"] == first.json()["decision_ids"]


def test_local_demo_seed_is_unavailable_outside_development() -> None:
    app = create_app()
    settings = get_api_settings()
    app.dependency_overrides[get_api_settings] = lambda: replace(
        settings, environment="staging"
    )

    response = TestClient(app).post("/api/v1/local/demo/seed")

    assert response.status_code == 403
