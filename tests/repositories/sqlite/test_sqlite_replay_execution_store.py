from __future__ import annotations

from datetime import UTC, datetime

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.repositories.sqlite.sqlite_replay_execution_store import (
    SQLiteReplayExecutionStore,
)
from ai_governance.tenancy.domain import TenantContext


def test_execution_store_is_shared_by_independent_process_style_instances(tmp_path) -> None:
    database_path = tmp_path / "replay.db"
    database = SQLiteDatabase(database_path)
    database.initialize()
    writer = SQLiteReplayExecutionStore(database)
    reader = SQLiteReplayExecutionStore(SQLiteDatabase(database_path))
    source = WorkflowExecution(
        workflow_id="workflow-1",
        execution_id="execution-1",
        workflow_name="Workflow",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={"input": True},
        final_state={"state": True},
        events=[{"type": "COMPLETED"}],
        organization_id="org-1",
        project_id="project-1",
        input_snapshot_ref="input:1",
        state_snapshot_ref="state:1",
        metadata={"source": "test"},
        created_at=datetime(2026, 7, 17, tzinfo=UTC),
    )

    writer.upsert(source)
    loaded = reader.get_execution(
        "execution-1", TenantContext("org-1", "project-1", "actor", "request")
    )

    assert loaded == source
    assert reader.get_execution(
        "execution-1", TenantContext("another-org", "project-1", "actor", "request")
    ) is None
