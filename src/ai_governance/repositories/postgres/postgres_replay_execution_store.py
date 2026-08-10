"""PostgreSQL storage for immutable Replay source and produced executions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.repositories.replay_execution_store import (
    workflow_execution_from_payload,
    workflow_execution_payload,
)
from ai_governance.tenancy.domain import TenantContext


@final
class PostgresReplayExecutionStore:
    """Tenant-scoped execution evidence shared by API and worker processes."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def get_execution(
        self, execution_id: str, context: TenantContext
    ) -> WorkflowExecution | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json::text AS payload_json FROM replay_workflow_execution
                WHERE organization_id=%(organization_id)s
                  AND project_id=%(project_id)s
                  AND execution_id=%(execution_id)s
                """,
                {
                    "organization_id": context.organization_id,
                    "project_id": context.project_id or "",
                    "execution_id": execution_id,
                },
            ).fetchone()
        return (
            workflow_execution_from_payload(json.loads(row["payload_json"]))
            if row
            else None
        )

    def upsert(self, execution: WorkflowExecution) -> None:
        """Persist a historical or produced execution under its immutable ID."""
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO replay_workflow_execution (
                    organization_id, project_id, execution_id, payload_json, updated_at
                ) VALUES (
                    %(organization_id)s, %(project_id)s, %(execution_id)s,
                    %(payload_json)s::jsonb, %(updated_at)s
                ) ON CONFLICT (organization_id, project_id, execution_id) DO UPDATE SET
                    payload_json=EXCLUDED.payload_json,
                    updated_at=EXCLUDED.updated_at
                """,
                {
                    "organization_id": execution.organization_id,
                    "project_id": execution.project_id,
                    "execution_id": execution.execution_id,
                    "payload_json": json.dumps(
                        workflow_execution_payload(execution),
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ),
                    "updated_at": execution.created_at or datetime.now(UTC),
                },
            )
            connection.commit()

    def save(self, execution: WorkflowExecution) -> None:
        """Alias used by ``ReplayExecutionStore`` for produced executions."""
        self.upsert(execution)
