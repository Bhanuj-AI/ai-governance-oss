"""SQLite persistence for agent execution traces."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from threading import Lock
from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
    ToolCallContext,
    WorkflowStep,
    WorkflowStepLifecycle,
)
from ai_governance.domain.agent_execution.agent_execution_event import ActorType
from ai_governance.domain.agent_execution.errors import (
    AgentExecutionConcurrencyConflict,
    AgentExecutionIdempotencyConflict,
    AgentExecutionRuntimeToolCallConflict,
)
from ai_governance.repositories.agent_execution_repository import (
    AgentExecutionAgentListFilters,
    AgentExecutionAgentSummary,
    AgentExecutionEventListFilters,
    AgentExecutionEventRepository,
    AgentExecutionListFilters,
    AgentExecutionRepository,
)


@final
class SQLiteAgentExecutionRepository(AgentExecutionRepository):
    """SQLite-backed AgentExecution repository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._lock = Lock()

    def save(self, execution: AgentExecution) -> AgentExecution:
        with self._lock, self._database.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO agent_execution (
                    execution_id, organization_id, project_id, agent_id,
                    agent_name, agent_version, external_execution_id,
                    runtime_provider, status, started_at, completed_at,
                    correlation_id, parent_execution_id, metadata_json,
                    version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution.execution_id,
                    execution.organization_id,
                    execution.project_id or "",
                    execution.agent_id,
                    execution.agent_name,
                    execution.agent_version,
                    execution.external_execution_id,
                    execution.runtime_provider,
                    execution.status.value,
                    execution.started_at.isoformat(),
                    execution.completed_at.isoformat()
                    if execution.completed_at
                    else None,
                    execution.correlation_id,
                    execution.parent_execution_id,
                    json.dumps(dict(execution.metadata), sort_keys=True, default=str),
                    execution.version,
                    execution.created_at.isoformat(),
                    execution.updated_at.isoformat(),
                ),
            )
            connection.commit()
        return execution

    def get(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecution | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM agent_execution
                WHERE organization_id=? AND project_id=? AND execution_id=?
                """,
                (organization_id, project_id or "", execution_id),
            ).fetchone()
        if row is None:
            return None
        return _execution_from_row(dict(row))

    def get_by_external_id(
        self,
        external_execution_id: str,
        runtime_provider: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecution | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM agent_execution
                WHERE organization_id=? AND project_id=?
                  AND external_execution_id=? AND runtime_provider=?
                """,
                (
                    organization_id,
                    project_id or "",
                    external_execution_id,
                    runtime_provider,
                ),
            ).fetchone()
        if row is None:
            return None
        return _execution_from_row(dict(row))

    def list(
        self,
        filters: AgentExecutionListFilters,
        organization_id: str,
        project_id: str | None = None,
    ) -> list[AgentExecution]:
        conditions = ["organization_id=?", "project_id=?"]
        params: list = [organization_id, project_id or ""]

        if filters.agent_id is not None:
            conditions.append("agent_id=?")
            params.append(filters.agent_id)
        if filters.status is not None:
            conditions.append("status=?")
            params.append(filters.status.value)
        if filters.runtime_provider is not None:
            conditions.append("runtime_provider=?")
            params.append(filters.runtime_provider)
        if filters.created_after is not None:
            conditions.append("created_at>=?")
            params.append(filters.created_after.isoformat())
        if filters.created_before is not None:
            conditions.append("created_at<=?")
            params.append(filters.created_before.isoformat())

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT * FROM agent_execution
            WHERE {where_clause}
            ORDER BY created_at DESC, execution_id DESC
            LIMIT ?
        """
        params.append(filters.limit)

        with self._database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_execution_from_row(dict(row)) for row in rows]

    def list_agents(
        self,
        filters: AgentExecutionAgentListFilters,
        organization_id: str,
        project_id: str | None = None,
    ) -> list[AgentExecutionAgentSummary]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT agent_id, agent_name, runtime_provider,
                       COUNT(*) AS execution_count,
                       SUM(CASE WHEN status='SUCCEEDED' THEN 1 ELSE 0 END) AS succeeded_count,
                       SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed_count,
                       SUM(CASE WHEN status='RUNNING' THEN 1 ELSE 0 END) AS running_count,
                       MAX(started_at) AS last_started_at
                FROM agent_execution
                WHERE organization_id=? AND project_id=?
                GROUP BY agent_id, agent_name, runtime_provider
                ORDER BY last_started_at DESC, agent_id ASC, runtime_provider ASC
                LIMIT ? OFFSET ?
                """,
                (organization_id, project_id or "", filters.limit, filters.offset),
            ).fetchall()
        return [
            AgentExecutionAgentSummary(
                agent_id=row["agent_id"],
                agent_name=row["agent_name"],
                runtime_provider=row["runtime_provider"],
                execution_count=row["execution_count"],
                succeeded_count=row["succeeded_count"],
                failed_count=row["failed_count"],
                running_count=row["running_count"],
                last_started_at=datetime.fromisoformat(row["last_started_at"]),
            )
            for row in rows
        ]

    def update_status(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None,
        new_status: AgentExecutionStatus,
        completed_at: datetime | None,
        expected_version: int,
    ) -> AgentExecution:
        with self._lock, self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT version FROM agent_execution
                WHERE execution_id=? AND organization_id=? AND project_id=?
                """,
                (execution_id, organization_id, project_id or ""),
            ).fetchone()
            if row is None:
                raise ValueError(f"Execution '{execution_id}' not found.")
            if row["version"] != expected_version:
                raise AgentExecutionConcurrencyConflict(
                    f"Version mismatch for execution '{execution_id}'."
                )
            now = datetime.now(UTC)
            connection.execute(
                """
                UPDATE agent_execution
                SET status=?, completed_at=?, version=version+1, updated_at=?
                WHERE execution_id=? AND organization_id=? AND project_id=? AND version=?
                """,
                (
                    new_status.value,
                    completed_at.isoformat() if completed_at else None,
                    now.isoformat(),
                    execution_id,
                    organization_id,
                    project_id or "",
                    expected_version,
                ),
            )
            connection.commit()
        return self.get(execution_id, organization_id, project_id) or AgentExecution(
            execution_id=execution_id,
            organization_id=organization_id,
            project_id=project_id,
            agent_id="",
            agent_name="",
            agent_version="",
            external_execution_id="",
            runtime_provider="",
            status=new_status,
            started_at=now,
            completed_at=completed_at,
            correlation_id=None,
            parent_execution_id=None,
            created_at=now,
            updated_at=now,
        )


@final
class SQLiteAgentExecutionEventRepository(AgentExecutionEventRepository):
    """SQLite-backed append-only AgentExecutionEvent repository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._lock = Lock()

    def save(
        self,
        event: AgentExecutionEvent,
        idempotency_key: str | None = None,
    ) -> AgentExecutionEvent:
        with self._lock, self._database.connect() as connection:
            try:
                connection.execute(
                    """
                        INSERT INTO agent_execution_event (
                            event_id, execution_id, organization_id, project_id,
                            event_type, sequence_number, occurred_at, received_at, late_for_runtime_findings, runtime_findings_finalization_cutoff_at, runtime_findings_lateness_policy_hours,
                            correlation_id, causation_id, actor_id, actor_type,
                            step_id, step_name, step_lifecycle, parent_step_id, source_kind,
                            tool_call_context_schema_version, runtime_tool_call_id,
                            tool_call_group_id, depends_on_tool_call_ids_json,
                            resource_references_json, evidence_references_json,
                            attributes_json, event_schema_version, idempotency_key,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                    (
                        event.event_id,
                        event.execution_id,
                        event.organization_id,
                        event.project_id or "",
                        event.event_type.value,
                        event.sequence_number,
                        event.occurred_at.isoformat(),
                        event.received_at.isoformat(),
                        int(event.late_for_runtime_findings),
                        event.runtime_findings_finalization_cutoff_at.isoformat()
                        if event.runtime_findings_finalization_cutoff_at
                        else None,
                        event.runtime_findings_lateness_policy_hours,
                        event.correlation_id,
                        event.causation_id,
                        event.actor_id,
                        event.actor_type.value if event.actor_type else None,
                        event.workflow_step.step_id if event.workflow_step else None,
                        event.workflow_step.step_name if event.workflow_step else None,
                        (
                            event.workflow_step.lifecycle.value
                            if event.workflow_step
                            else None
                        ),
                        (
                            event.workflow_step.parent_step_id
                            if event.workflow_step
                            else None
                        ),
                        event.workflow_step.source_kind
                        if event.workflow_step
                        else None,
                        (
                            event.tool_call_context.schema_version
                            if event.tool_call_context
                            else None
                        ),
                        (
                            event.tool_call_context.runtime_tool_call_id
                            if event.tool_call_context
                            else None
                        ),
                        (
                            event.tool_call_context.tool_call_group_id
                            if event.tool_call_context
                            else None
                        ),
                        json.dumps(
                            list(event.tool_call_context.depends_on_tool_call_ids)
                            if event.tool_call_context
                            else [],
                            separators=(",", ":"),
                        ),
                        json.dumps(
                            list(event.resource_references), separators=(",", ":")
                        ),
                        json.dumps(
                            list(event.evidence_references), separators=(",", ":")
                        ),
                        json.dumps(dict(event.attributes), sort_keys=True, default=str),
                        event.event_schema_version,
                        idempotency_key,
                        event.received_at.isoformat(),
                    ),
                )
                connection.commit()
            except Exception as exc:
                if "runtime_tool_call" in str(exc).lower():
                    raise AgentExecutionRuntimeToolCallConflict(
                        "Runtime tool-call ID conflict for execution "
                        f"'{event.execution_id}'."
                    ) from exc
                if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                    existing = self.find_by_idempotency_key(
                        idempotency_key or "",
                        event.execution_id,
                        event.organization_id,
                        event.project_id,
                    )
                    if existing is not None:
                        if (
                            existing.event_type is event.event_type
                            and dict(existing.attributes) == dict(event.attributes)
                            and existing.workflow_step == event.workflow_step
                            and existing.tool_call_context == event.tool_call_context
                        ):
                            return existing
                        raise AgentExecutionIdempotencyConflict(
                            f"Idempotency key conflict for execution '{event.execution_id}'."
                        ) from exc
                raise
        return event

    def get_by_id(
        self,
        event_id: str,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecutionEvent | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM agent_execution_event
                WHERE organization_id=? AND project_id=? AND event_id=? AND execution_id=?
                """,
                (organization_id, project_id or "", event_id, execution_id),
            ).fetchone()
        if row is None:
            return None
        return _event_from_row(dict(row))

    def list_by_execution(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
        filters: AgentExecutionEventListFilters | None = None,
    ) -> list[AgentExecutionEvent]:
        conditions = ["organization_id=?", "project_id=?", "execution_id=?"]
        params: list = [organization_id, project_id or "", execution_id]

        if filters is not None:
            if filters.event_type is not None:
                conditions.append("event_type=?")
                params.append(filters.event_type.value)
            if filters.actor_id is not None:
                conditions.append("actor_id=?")
                params.append(filters.actor_id)
            if filters.occurred_after is not None:
                conditions.append("occurred_at>=?")
                params.append(filters.occurred_after.isoformat())
            if filters.occurred_before is not None:
                conditions.append("occurred_at<=?")
                params.append(filters.occurred_before.isoformat())

        where_clause = " AND ".join(conditions)
        limit = filters.limit if filters else 200

        query = f"""
            SELECT * FROM agent_execution_event
            WHERE {where_clause}
            ORDER BY sequence_number ASC
            LIMIT ?
        """
        params.append(limit)

        with self._database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_event_from_row(dict(row)) for row in rows]

    def find_by_idempotency_key(
        self,
        idempotency_key: str,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecutionEvent | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM agent_execution_event
                WHERE organization_id=? AND project_id=? AND execution_id=? AND idempotency_key=?
                """,
                (organization_id, project_id or "", execution_id, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        return _event_from_row(dict(row))

    def max_sequence_number(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> int:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence_number), 0) AS max_seq
                FROM agent_execution_event
                WHERE organization_id=? AND project_id=? AND execution_id=?
                """,
                (organization_id, project_id or "", execution_id),
            ).fetchone()
        return int(row["max_seq"]) if row else 0


# -- Payload mappers ----------------------------------------------------------


def _execution_from_row(row: dict) -> AgentExecution:
    return AgentExecution(
        execution_id=row["execution_id"],
        organization_id=row["organization_id"],
        project_id=row["project_id"] or None,
        agent_id=row["agent_id"],
        agent_name=row["agent_name"],
        agent_version=row["agent_version"],
        external_execution_id=row["external_execution_id"],
        runtime_provider=row["runtime_provider"],
        status=AgentExecutionStatus(row["status"]),
        started_at=datetime.fromisoformat(row["started_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"])
            if row.get("completed_at")
            else None
        ),
        correlation_id=row["correlation_id"],
        parent_execution_id=row["parent_execution_id"],
        metadata=json.loads(row["metadata_json"]) if row.get("metadata_json") else {},
        version=row["version"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _event_from_row(row: dict) -> AgentExecutionEvent:
    return AgentExecutionEvent(
        event_id=row["event_id"],
        execution_id=row["execution_id"],
        organization_id=row["organization_id"],
        project_id=row["project_id"] or None,
        event_type=EventType(row["event_type"]),
        sequence_number=row["sequence_number"],
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        received_at=datetime.fromisoformat(row["received_at"]),
        late_for_runtime_findings=bool(row.get("late_for_runtime_findings", False)),
        runtime_findings_finalization_cutoff_at=datetime.fromisoformat(
            row["runtime_findings_finalization_cutoff_at"]
        )
        if row.get("runtime_findings_finalization_cutoff_at")
        else None,
        runtime_findings_lateness_policy_hours=row.get(
            "runtime_findings_lateness_policy_hours"
        ),
        correlation_id=row["correlation_id"],
        causation_id=row["causation_id"],
        actor_id=row["actor_id"],
        actor_type=ActorType(row["actor_type"]) if row.get("actor_type") else None,
        workflow_step=_workflow_step_from_row(row),
        tool_call_context=_tool_call_context_from_row(row),
        resource_references=json.loads(row["resource_references_json"])
        if row.get("resource_references_json")
        else [],
        evidence_references=json.loads(row["evidence_references_json"])
        if row.get("evidence_references_json")
        else [],
        attributes=json.loads(row["attributes_json"])
        if row.get("attributes_json")
        else {},
        event_schema_version=row.get("event_schema_version", "1"),
    )


def _workflow_step_from_row(row: dict) -> WorkflowStep | None:
    if row.get("step_id") is None:
        return None
    return WorkflowStep(
        step_id=row["step_id"],
        step_name=row["step_name"],
        lifecycle=WorkflowStepLifecycle(row["step_lifecycle"]),
        parent_step_id=row.get("parent_step_id"),
        source_kind=row.get("source_kind"),
    )


def _tool_call_context_from_row(row: dict) -> ToolCallContext | None:
    if row.get("runtime_tool_call_id") is None:
        return None
    return ToolCallContext(
        schema_version=row["tool_call_context_schema_version"],
        runtime_tool_call_id=row["runtime_tool_call_id"],
        tool_call_group_id=row["tool_call_group_id"],
        depends_on_tool_call_ids=tuple(
            json.loads(row["depends_on_tool_call_ids_json"])
            if row.get("depends_on_tool_call_ids_json")
            else []
        ),
    )
