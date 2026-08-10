from datetime import UTC, datetime

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.repositories.sqlite.sqlite_replay_execution_catalog import (
    SQLiteReplayExecutionCatalog,
)
from ai_governance.services.replay_execution_discovery import (
    ReplayExecutionProjection,
    ReplayExecutionSearchFilters,
)
from ai_governance.tenancy.domain import TenantContext


def test_catalog_is_durable_and_cursor_paginated(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "catalog.db")
    database.initialize()
    catalog = SQLiteReplayExecutionCatalog(database)
    context = TenantContext("org-1", "project-1", "actor-1", "request-1")
    catalog.upsert(_projection("execution-1", 1), context)
    catalog.upsert(_projection("execution-2", 2), context)

    first = catalog.search(ReplayExecutionSearchFilters(limit=1), context)
    restarted = SQLiteReplayExecutionCatalog(SQLiteDatabase(tmp_path / "catalog.db"))
    second = restarted.search(
        ReplayExecutionSearchFilters(limit=1, cursor=first.next_cursor), context
    )

    assert [item.execution_id for item in first.items] == ["execution-2"]
    assert [item.execution_id for item in second.items] == ["execution-1"]
    assert restarted.get("execution-1", context) is not None


def _projection(execution_id: str, day: int) -> ReplayExecutionProjection:
    timestamp = datetime(2026, 1, day, tzinfo=UTC)
    return ReplayExecutionProjection(
        execution_id=execution_id,
        organization_id="org-1",
        project_id="project-1",
        workflow_id="workflow",
        workflow_name="Workflow",
        workflow_version="1",
        execution_status="COMPLETED",
        executed_at=timestamp,
        completed_at=timestamp,
        actor_id="actor-1",
        actor_type="USER",
        replayable=True,
        replayability_code=None,
        replayability_summary=None,
        evaluation_available=True,
        created_at=timestamp,
        updated_at=timestamp,
    )
