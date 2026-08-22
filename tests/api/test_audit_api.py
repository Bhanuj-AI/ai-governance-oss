from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import (
    get_job_repository,
    get_mcp_audit_log,
    get_mcp_invocation_audit_log,
)
from ai_governance.domain.jobs import Job, JobStatus, JobType
from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.mcp.dto import WriteEnvelope
from ai_governance.mcp.invocation_audit import MCPInvocationAuditLog
from ai_governance.repositories import InMemoryJobRepository


def _client() -> tuple[TestClient, MCPExecutionAuditLog, InMemoryJobRepository]:
    audit_log = MCPExecutionAuditLog.in_memory()
    job_repository = InMemoryJobRepository()
    app = create_app()
    app.dependency_overrides[get_mcp_audit_log] = lambda: audit_log
    app.dependency_overrides[get_job_repository] = lambda: job_repository
    return TestClient(app), audit_log, job_repository


def test_list_audit_page_returns_summary_filters_and_pagination() -> None:
    client, audit_log, job_repository = _client()
    job_repository.save(_job("job-1", JobStatus.FAILED))
    _completed_record(
        audit_log,
        request_id="request-1",
        correlation_id="corr-1",
        tool_name="job.retry",
        actor_id="agent-1",
        status="SUCCEEDED",
        job_id="job-1",
        started_at=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
    )
    _completed_record(
        audit_log,
        request_id="request-2",
        correlation_id="corr-2",
        tool_name="evaluation.submit_async",
        actor_id="agent-2",
        status="FAILED",
        started_at=datetime(2026, 7, 8, 12, 2, tzinfo=UTC),
    )
    _completed_record(
        audit_log,
        request_id="request-3",
        correlation_id="corr-1",
        tool_name="experiment.run_async",
        actor_id="agent-1",
        status="DRY_RUN",
        dry_run=True,
        started_at=datetime(2026, 7, 8, 12, 4, tzinfo=UTC),
    )
    _stale_started_record(
        audit_log,
        request_id="request-4",
        correlation_id="corr-4",
        tool_name="job.retry",
        actor_id="agent-1",
    )

    response = client.get(
        "/api/v1/audit",
        params={
            "actor_id": "agent-1",
            "limit": 2,
            "offset": 0,
            "interrupted_after_seconds": 60,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert len(payload["records"]) == 2
    assert any(record["request_id"] == "request-3" for record in payload["records"])
    assert payload["filters"]["tool_names"] == [
        "evaluation.submit_async",
        "experiment.run_async",
        "job.retry",
    ]
    assert {metric["label"]: metric["value"] for metric in payload["summary"]} == {
        "Started": 0,
        "Interrupted": 1,
        "Succeeded": 1,
        "Failed": 0,
        "Dry Run": 1,
    }


def test_lists_read_only_mcp_invocations_separately_from_mutations() -> None:
    client, _audit_log, _job_repository = _client()
    invocation_log = MCPInvocationAuditLog.in_memory()
    client.app.dependency_overrides[get_mcp_invocation_audit_log] = lambda: (
        invocation_log
    )
    received = invocation_log.received(
        invocation_id="invocation-1",
        request_id="request-1",
        correlation_id="correlation-1",
        tool_name="provider.list",
        organization_id="org_default",
        project_id=None,
        actor_id="user-1",
        actor_type="USER",
        client_id="copilot",
        authorization_decision="ALLOWED",
        payload={"token": "must be redacted"},
    )
    invocation_log.complete(
        received,
        status="SUCCEEDED",
        authorization_decision="ALLOWED",
        response={"providers": []},
    )

    response = client.get("/api/v1/audit/invocations")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["records"][0]["tool_name"] == "provider.list"
    assert "argument_summary" not in response.json()["records"][0]


def test_list_audit_page_supports_search_and_interrupted_filter() -> None:
    client, audit_log, job_repository = _client()
    job_repository.save(_job("job-1", JobStatus.SUCCEEDED))
    _completed_record(
        audit_log,
        request_id="request-search",
        correlation_id="corr-search",
        tool_name="job.cancel",
        actor_id="agent-1",
        status="SUCCEEDED",
        job_id="job-1",
        started_at=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
    )
    _stale_started_record(
        audit_log,
        request_id="request-stale",
        correlation_id="corr-stale",
        tool_name="job.retry",
        actor_id="agent-2",
    )

    search_response = client.get(
        "/api/v1/audit",
        params={"search": "job-1"},
    )
    interrupted_response = client.get(
        "/api/v1/audit",
        params={"interrupted": "true", "interrupted_after_seconds": 60},
    )

    assert search_response.status_code == 200
    assert search_response.json()["total"] == 1
    assert search_response.json()["records"][0]["job_id"] == "job-1"
    assert interrupted_response.status_code == 200
    assert interrupted_response.json()["total"] == 1
    assert interrupted_response.json()["records"][0]["interrupted"] is True


def test_get_audit_detail_includes_linked_job_and_related_records() -> None:
    client, audit_log, job_repository = _client()
    job_repository.save(_job("job-1", JobStatus.CANCELLED))
    record = _completed_record(
        audit_log,
        request_id="request-1",
        correlation_id="corr-shared",
        tool_name="job.cancel",
        actor_id="agent-1",
        status="SUCCEEDED",
        job_id="job-1",
        started_at=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
    )
    _completed_record(
        audit_log,
        request_id="request-2",
        correlation_id="corr-shared",
        tool_name="experiment.run_async",
        actor_id="agent-1",
        status="DRY_RUN",
        dry_run=True,
        started_at=datetime(2026, 7, 8, 12, 5, tzinfo=UTC),
    )

    response = client.get(f"/api/v1/audit/{record.audit_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["linked_job"]["job_id"] == "job-1"
    assert payload["linked_job"]["status"] == "CANCELLED"
    assert len(payload["related_records"]) == 1
    assert payload["related_records"][0]["correlation_id"] == "corr-shared"


def test_get_audit_detail_returns_404_for_missing_record() -> None:
    client, _, _ = _client()

    response = client.get("/api/v1/audit/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AUDIT_RECORD_NOT_FOUND"


def _completed_record(
    audit_log: MCPExecutionAuditLog,
    *,
    request_id: str,
    correlation_id: str,
    tool_name: str,
    actor_id: str,
    status: str,
    started_at: datetime,
    dry_run: bool = False,
    job_id: str | None = None,
):
    envelope = WriteEnvelope(
        request_id=request_id,
        correlation_id=correlation_id,
        idempotency_key=f"idem-{request_id}",
        requested_by=actor_id,
        actor_type="AGENT",
        reason="studio audit page test",
        dry_run=dry_run,
    )
    record = audit_log.start(
        tool_name=tool_name,
        operation_type=tool_name.upper().replace(".", "_"),
        resource_type="job" if "job." in tool_name else "evaluation",
        resource_id=job_id or "resource-1",
        envelope=envelope,
        payload={
            "request_id": request_id,
            "provider_config": {"api_key": "secret"},
        },
    )
    audit_log.save_record(replace(record, started_at=started_at))
    return audit_log.complete(
        replace(record, started_at=started_at),
        status=status,
        job_id=job_id,
    )


def _stale_started_record(
    audit_log: MCPExecutionAuditLog,
    *,
    request_id: str,
    correlation_id: str,
    tool_name: str,
    actor_id: str,
):
    envelope = WriteEnvelope(
        request_id=request_id,
        correlation_id=correlation_id,
        idempotency_key=f"idem-{request_id}",
        requested_by=actor_id,
        actor_type="AGENT",
        reason="stale started audit",
    )
    record = audit_log.start(
        tool_name=tool_name,
        operation_type=tool_name.upper().replace(".", "_"),
        resource_type="job",
        resource_id="job-stale",
        envelope=envelope,
        payload={"job_id": "job-stale"},
    )
    stale = replace(
        record,
        started_at=datetime.now(UTC) - timedelta(seconds=120),
    )
    audit_log.save_record(stale)
    return stale


def _job(
    job_id: str,
    status: JobStatus,
) -> Job:
    now = datetime(2026, 7, 8, 11, 0, tzinfo=UTC)
    return Job(
        job_id=job_id,
        job_type=JobType.REPLAY,
        status=status,
        input_refs={"job_id": job_id},
        input_hash=f"hash-{job_id}",
        idempotency_key=f"key-{job_id}",
        submitted_by="tester",
        attempt_count=1,
        max_attempts=3,
        result_ref=None,
        failure_reason=None,
        leased_by=None,
        lease_expires_at=None,
        heartbeat_at=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now
        if status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
        else None,
    )
