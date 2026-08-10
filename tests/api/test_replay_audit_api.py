from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import get_replay_audit_service
from ai_governance.services.replay_audit_service import ReplayAuditRecord


class _ReplayAuditService:
    def list_records(self, replay_id: str, context):
        assert replay_id == "replay-1"
        assert context.organization_id == "org_default"
        return (
            ReplayAuditRecord(
                event_id="replay-1:REPLAY_EXECUTION:job-1",
                operation_type="REPLAY_EXECUTION",
                status="SUCCEEDED",
                occurred_at=datetime(2026, 8, 6, 5, 0, tzinfo=UTC),
                resource_type="Job",
                resource_id="job-1",
                detail="REPLAY_EXECUTION job is succeeded.",
                job_id="job-1",
                result_reference="workflow_execution:execution-1",
            ),
        )


def test_replay_audit_endpoint_returns_the_replay_scoped_timeline() -> None:
    app = create_app()
    app.dependency_overrides[get_replay_audit_service] = _ReplayAuditService

    response = TestClient(app).get("/api/v1/replays/replay-1/audit")

    assert response.status_code == 200
    assert response.json() == [
        {
            "event_id": "replay-1:REPLAY_EXECUTION:job-1",
            "operation_type": "REPLAY_EXECUTION",
            "status": "SUCCEEDED",
            "occurred_at": "2026-08-06T05:00:00Z",
            "resource_type": "Job",
            "resource_id": "job-1",
            "detail": "REPLAY_EXECUTION job is succeeded.",
            "job_id": "job-1",
            "result_reference": "workflow_execution:execution-1",
        }
    ]
