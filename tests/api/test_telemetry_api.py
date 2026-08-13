from fastapi.testclient import TestClient

from ai_governance.api.app import create_app


def test_telemetry_status_and_preview_are_read_only() -> None:
    app = create_app()
    client = TestClient(app)
    headers = {
        "X-AI-Governance-Organization-Id": "org_default",
        "X-AI-Governance-Project-Id": "project_default",
        "X-AI-Governance-Actor-Id": "local-admin",
    }
    before = app.state.telemetry_service.status()["pending_snapshots"]

    status = client.get("/api/v1/telemetry/status", headers=headers)
    preview = client.get("/api/v1/telemetry/preview", headers=headers)

    assert status.status_code == 200
    assert status.json()["installation_id"]
    assert preview.status_code == 200
    assert app.state.telemetry_service.status()["pending_snapshots"] == before
