"""Durable authoritative workflow-execution storage for local Replay workers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.repositories.replay_execution_store import (
    workflow_execution_from_payload,
    workflow_execution_payload,
)
from ai_governance.tenancy.domain import TenantContext


@final
class SQLiteReplayExecutionStore:
    """Tenant-scoped source and produced-execution store shared by API and workers.

    This is intentionally separate from the replay discovery catalog: the catalog
    is compact search data, whereas this store retains the frozen execution
    payload needed to reconstruct and evaluate a replay.  It is suitable for
    local and Docker SQLite deployments; production workflow systems should
    provide their own authoritative adapter behind the same two methods.
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get_execution(
        self, execution_id: str, context: TenantContext
    ) -> WorkflowExecution | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM replay_workflow_execution
                WHERE organization_id=? AND project_id=? AND execution_id=?
                """,
                (context.organization_id, context.project_id or "", execution_id),
            ).fetchone()
        return (
            workflow_execution_from_payload(json.loads(row["payload_json"]))
            if row
            else None
        )

    def upsert(self, execution: WorkflowExecution) -> None:
        """Persist a historical or produced execution under its immutable ID."""
        payload = workflow_execution_payload(execution)
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO replay_workflow_execution (
                    organization_id, project_id, execution_id, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(organization_id, project_id, execution_id) DO UPDATE SET
                    payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (
                    execution.organization_id,
                    execution.project_id,
                    execution.execution_id,
                    json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str),
                    (execution.created_at or datetime.now(UTC)).isoformat(),
                ),
            )
            connection.commit()

    def save(self, execution: WorkflowExecution) -> None:
        """Alias used by ``ReplayExecutionStore`` for produced executions."""
        self.upsert(execution)
