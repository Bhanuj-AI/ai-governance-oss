from __future__ import annotations

from kavach.databases.postgres.database import PostgresDatabase
from kavach.mcp.audit import (
    MCPExecutionAuditLog,
    PostgresMCPExecutionAuditStore,
)
from kavach.mcp.dto import WriteEnvelope


def test_postgres_audit_log_persists_completed_record(
    postgres_database: PostgresDatabase,
) -> None:
    log = MCPExecutionAuditLog(PostgresMCPExecutionAuditStore(postgres_database))
    envelope = WriteEnvelope(
        request_id="request-1",
        idempotency_key="idem-1",
        requested_by="agent-1",
        actor_type="AGENT",
        reason="governed write",
        metadata={"ticket": "KAV-1"},
    )

    started = log.start(
        tool_name="evaluation.submit_async",
        operation_type="SUBMIT_EVALUATION_JOB",
        resource_type="evaluation",
        resource_id="execution-1",
        envelope=envelope,
        payload={"provider_config": {"api_key": "secret"}},
        resolved_versions={"provider_name": "mock"},
    )
    log.complete(
        started,
        status="SUCCEEDED",
        job_id="job-1",
        result_reference="job:job-1",
    )

    reopened = MCPExecutionAuditLog(PostgresMCPExecutionAuditStore(postgres_database))
    records = reopened.list_records()

    assert len(records) == 1
    assert records[0].audit_id == started.audit_id
    assert records[0].status == "SUCCEEDED"
    assert records[0].job_id == "job-1"
    assert records[0].request_summary["provider_config"] == "<redacted>"
    assert records[0].resolved_versions == {"provider_name": "mock"}
