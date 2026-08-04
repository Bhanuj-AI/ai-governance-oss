from __future__ import annotations

from kavach.mcp.audit import MCPExecutionAuditLog
from kavach.ontology.demo_seed import seed_demo_mcp_audit_log


def test_demo_mcp_audit_seed_is_durable_and_idempotent(tmp_path) -> None:
    database_path = tmp_path / "mcp_execution_audit.db"
    audit_log = MCPExecutionAuditLog.sqlite(database_path)

    seeded_ids = seed_demo_mcp_audit_log(audit_log)
    seed_demo_mcp_audit_log(audit_log)

    reopened = MCPExecutionAuditLog.sqlite(database_path)
    records = reopened.list_records()

    assert seeded_ids
    assert {record.audit_id for record in records} == set(seeded_ids)
    assert any(
        record.audit_id == "audit-demo-experiment-add-candidate"
        for record in records
    )
