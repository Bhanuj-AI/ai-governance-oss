from __future__ import annotations

from pathlib import Path

from ai_governance import __version__
from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.mcp.audit import (
    MCPExecutionAuditLog,
    PostgresMCPExecutionAuditStore,
    request_hash,
)
from ai_governance.mcp.dto import WriteEnvelope


def test_sqlite_audit_log_persists_completed_record(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "mcp-audit.db"
    envelope = WriteEnvelope(
        request_id="request-1",
        idempotency_key="idem-1",
        requested_by="agent-1",
        actor_type="AGENT",
        reason="governed write",
        metadata={"ticket": "KAV-1"},
    )

    audit_log = MCPExecutionAuditLog.sqlite(database_path)
    record = audit_log.start(
        tool_name="evaluation.submit_async",
        operation_type="SUBMIT_EVALUATION_JOB",
        resource_type="evaluation",
        resource_id="execution-1",
        envelope=envelope,
        payload={
            "execution_id": "execution-1",
            "provider_config": {"api_key": "secret"},
        },
        resolved_versions={"provider_name": "mock"},
    )
    audit_log.complete(
        record,
        status="SUCCEEDED",
        job_id="job-1",
        result_reference="job:job-1",
    )

    reopened = MCPExecutionAuditLog.sqlite(database_path)

    records = reopened.list_records()
    assert len(records) == 1
    assert records[0].audit_id == record.audit_id
    assert records[0].tool_version == __version__
    assert records[0].status == "SUCCEEDED"
    assert records[0].job_id == "job-1"
    assert records[0].request_summary["provider_config"] == "<redacted>"
    assert records[0].resolved_versions == {"provider_name": "mock"}


def test_sqlite_audit_log_keeps_started_record_after_start(
    tmp_path: Path,
) -> None:
    audit_log = MCPExecutionAuditLog.sqlite(tmp_path / "mcp-audit.db")
    envelope = WriteEnvelope(
        request_id="request-1",
        idempotency_key="idem-1",
        requested_by="agent-1",
        actor_type="AGENT",
        reason="governed write",
    )

    audit_log.start(
        tool_name="job.cancel",
        operation_type="CANCEL_JOB",
        resource_type="job",
        resource_id="job-1",
        envelope=envelope,
        payload={"job_id": "job-1"},
    )

    records = audit_log.list_records()
    assert len(records) == 1
    assert records[0].status == "STARTED"
    assert records[0].completed_at is None


def test_postgres_audit_log_constructs_postgres_store(monkeypatch) -> None:
    monkeypatch.setattr(PostgresDatabase, "initialize", lambda _database: None)

    audit_log = MCPExecutionAuditLog.postgres(
        "postgresql://audit:secret@db.example/ai-governance"
    )

    assert isinstance(audit_log._store, PostgresMCPExecutionAuditStore)


def test_request_hash_is_stable_for_semantically_identical_payloads() -> None:
    left = {"b": 2, "a": {"d": 4, "c": 3}}
    right = {"a": {"c": 3, "d": 4}, "b": 2}

    assert request_hash(left) == request_hash(right)
