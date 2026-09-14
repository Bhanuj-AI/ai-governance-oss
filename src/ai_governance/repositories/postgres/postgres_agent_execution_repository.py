"""PostgreSQL persistence for agent execution traces.

Provides tenant-scoped, idempotent storage for AgentExecution aggregates
and append-only AgentExecutionEvents.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
    WorkflowStep,
    WorkflowStepLifecycle,
)
from ai_governance.domain.agent_execution.agent_execution_event import ActorType
from ai_governance.domain.agent_execution.errors import (
    AgentExecutionConcurrencyConflict,
    AgentExecutionIdempotencyConflict,
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
class PostgresAgentExecutionRepository(AgentExecutionRepository):
    """PostgreSQL-backed AgentExecution repository."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, execution: AgentExecution) -> AgentExecution:
        """Persist or upsert an execution.

        Handles two conflict scenarios atomically:
        1. Primary key (execution_id) — upserts the row.
        2. External ID unique index — a concurrent duplicate ingestion
           already created the execution; return it instead of failing.
        """
        with self._database.connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO agent_execution (
                        execution_id, organization_id, project_id, agent_id,
                        agent_name, agent_version, external_execution_id,
                        runtime_provider, status, started_at, completed_at,
                        correlation_id, parent_execution_id, metadata_json,
                        version, created_at, updated_at
                    ) VALUES (
                        %(execution_id)s, %(organization_id)s, %(project_id)s,
                        %(agent_id)s, %(agent_name)s, %(agent_version)s,
                        %(external_execution_id)s, %(runtime_provider)s,
                        %(status)s, %(started_at)s, %(completed_at)s,
                        %(correlation_id)s, %(parent_execution_id)s,
                        %(metadata_json)s, %(version)s, %(created_at)s,
                        %(updated_at)s
                    ) ON CONFLICT (organization_id, project_id, execution_id) DO UPDATE SET
                        agent_id=EXCLUDED.agent_id,
                        agent_name=EXCLUDED.agent_name,
                        agent_version=EXCLUDED.agent_version,
                        external_execution_id=EXCLUDED.external_execution_id,
                        runtime_provider=EXCLUDED.runtime_provider,
                        status=EXCLUDED.status,
                        started_at=EXCLUDED.started_at,
                        completed_at=EXCLUDED.completed_at,
                        correlation_id=EXCLUDED.correlation_id,
                        parent_execution_id=EXCLUDED.parent_execution_id,
                        metadata_json=EXCLUDED.metadata_json,
                        version=EXCLUDED.version,
                        updated_at=EXCLUDED.updated_at
                    """,
                    {
                        "execution_id": execution.execution_id,
                        "organization_id": execution.organization_id,
                        "project_id": execution.project_id or "",
                        "agent_id": execution.agent_id,
                        "agent_name": execution.agent_name,
                        "agent_version": execution.agent_version,
                        "external_execution_id": execution.external_execution_id,
                        "runtime_provider": execution.runtime_provider,
                        "status": execution.status.value,
                        "started_at": execution.started_at,
                        "completed_at": execution.completed_at,
                        "correlation_id": execution.correlation_id,
                        "parent_execution_id": execution.parent_execution_id,
                        "metadata_json": json.dumps(
                            dict(execution.metadata),
                            sort_keys=True,
                            separators=(",", ":"),
                            default=str,
                        ),
                        "version": execution.version,
                        "created_at": execution.created_at,
                        "updated_at": execution.updated_at,
                    },
                )
                connection.commit()
            except Exception as exc:
                # Unique violation on (org, project, external_execution_id, runtime_provider)
                # means a concurrent duplicate ingestion already created this execution.
                if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                    existing = self.get_by_external_id(
                        execution.external_execution_id,
                        execution.runtime_provider,
                        execution.organization_id,
                        execution.project_id,
                    )
                    if existing is not None:
                        return existing
                raise
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
                SELECT execution_id, organization_id, project_id, agent_id,
                       agent_name, agent_version, external_execution_id,
                       runtime_provider, status, started_at, completed_at,
                       correlation_id, parent_execution_id, metadata_json,
                       version, created_at, updated_at
                FROM agent_execution
                WHERE organization_id=%(organization_id)s
                  AND project_id=%(project_id)s
                  AND execution_id=%(execution_id)s
                """,
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "execution_id": execution_id,
                },
            ).fetchone()
        if row is None:
            return None
        return _execution_from_row(row)

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
                SELECT execution_id, organization_id, project_id, agent_id,
                       agent_name, agent_version, external_execution_id,
                       runtime_provider, status, started_at, completed_at,
                       correlation_id, parent_execution_id, metadata_json,
                       version, created_at, updated_at
                FROM agent_execution
                WHERE organization_id=%(organization_id)s
                  AND project_id=%(project_id)s
                  AND external_execution_id=%(external_execution_id)s
                  AND runtime_provider=%(runtime_provider)s
                """,
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "external_execution_id": external_execution_id,
                    "runtime_provider": runtime_provider,
                },
            ).fetchone()
        if row is None:
            return None
        return _execution_from_row(row)

    def list(
        self,
        filters: AgentExecutionListFilters,
        organization_id: str,
        project_id: str | None = None,
    ) -> list[AgentExecution]:
        conditions = [
            "organization_id=%(organization_id)s",
            "project_id=%(project_id)s",
        ]
        params: dict = {
            "organization_id": organization_id,
            "project_id": project_id or "",
        }
        param_counter = 0

        if filters.agent_id is not None:
            param_counter += 1
            conditions.append(f"agent_id=%(agent_id_{param_counter})s")
            params[f"agent_id_{param_counter}"] = filters.agent_id

        if filters.status is not None:
            param_counter += 1
            conditions.append(f"status=%(status_{param_counter})s")
            params[f"status_{param_counter}"] = filters.status.value

        if filters.runtime_provider is not None:
            param_counter += 1
            conditions.append(f"runtime_provider=%(runtime_provider_{param_counter})s")
            params[f"runtime_provider_{param_counter}"] = filters.runtime_provider

        if filters.created_after is not None:
            param_counter += 1
            conditions.append(f"created_at>=%(created_after_{param_counter})s")
            params[f"created_after_{param_counter}"] = filters.created_after

        if filters.created_before is not None:
            param_counter += 1
            conditions.append(f"created_at<=%(created_before_{param_counter})s")
            params[f"created_before_{param_counter}"] = filters.created_before

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT execution_id, organization_id, project_id, agent_id,
                   agent_name, agent_version, external_execution_id,
                   runtime_provider, status, started_at, completed_at,
                   correlation_id, parent_execution_id, metadata_json,
                   version, created_at, updated_at
            FROM agent_execution
            WHERE {where_clause}
            ORDER BY created_at DESC, execution_id DESC
            LIMIT %(limit)s
        """
        params["limit"] = filters.limit

        with self._database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_execution_from_row(row) for row in rows]

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
                WHERE organization_id=%(organization_id)s AND project_id=%(project_id)s
                GROUP BY agent_id, agent_name, runtime_provider
                ORDER BY last_started_at DESC, agent_id ASC, runtime_provider ASC
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "limit": filters.limit,
                    "offset": filters.offset,
                },
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
                last_started_at=row["last_started_at"],
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
        with self._database.connect() as connection:
            result = connection.execute(
                """
                UPDATE agent_execution
                SET status=%(status)s,
                    completed_at=%(completed_at)s,
                    version=version+1,
                    updated_at=%(updated_at)s
                WHERE execution_id=%(execution_id)s
                  AND organization_id=%(organization_id)s
                  AND project_id=%(project_id)s
                  AND version=%(expected_version)s
                RETURNING execution_id, organization_id, project_id, agent_id,
                          agent_name, agent_version, external_execution_id,
                          runtime_provider, status, started_at, completed_at,
                          correlation_id, parent_execution_id, metadata_json,
                          version, created_at, updated_at
                """,
                {
                    "execution_id": execution_id,
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "status": new_status.value,
                    "completed_at": completed_at,
                    "expected_version": expected_version,
                    "updated_at": datetime.now(UTC),
                },
            ).fetchone()
            connection.commit()
        if result is None:
            raise AgentExecutionConcurrencyConflict(
                f"Version mismatch for execution '{execution_id}'."
            )
        return _execution_from_row(result)


@final
class PostgresAgentExecutionEventRepository(AgentExecutionEventRepository):
    """PostgreSQL-backed append-only AgentExecutionEvent repository."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(
        self,
        event: AgentExecutionEvent,
        idempotency_key: str | None = None,
    ) -> AgentExecutionEvent:
        """Persist an event atomically.

        Uses ``ON CONFLICT DO NOTHING`` on the idempotency-key unique index
        so that concurrent duplicate deliveries are resolved at the database
        level — no TOCTOU window between INSERT and SELECT.
        """
        with self._database.connect() as connection:
            result = connection.execute(
                """
                INSERT INTO agent_execution_event (
                    event_id, execution_id, organization_id, project_id,
                    event_type, sequence_number, occurred_at, received_at, late_for_runtime_findings, runtime_findings_finalization_cutoff_at, runtime_findings_lateness_policy_hours,
                    correlation_id, causation_id, actor_id, actor_type,
                    step_id, step_name, step_lifecycle, parent_step_id, source_kind,
                    resource_references_json, evidence_references_json,
                    attributes_json, event_schema_version, idempotency_key,
                    created_at
                ) VALUES (
                    %(event_id)s, %(execution_id)s, %(organization_id)s,
                    %(project_id)s, %(event_type)s, %(sequence_number)s,
                    %(occurred_at)s, %(received_at)s, %(late_for_runtime_findings)s, %(runtime_findings_finalization_cutoff_at)s, %(runtime_findings_lateness_policy_hours)s, %(correlation_id)s,
                    %(causation_id)s, %(actor_id)s, %(actor_type)s,
                    %(step_id)s, %(step_name)s, %(step_lifecycle)s, %(parent_step_id)s, %(source_kind)s,
                    %(resource_references_json)s, %(evidence_references_json)s,
                    %(attributes_json)s, %(event_schema_version)s,
                    %(idempotency_key)s, %(created_at)s
                ) ON CONFLICT (organization_id, project_id, execution_id, idempotency_key)
                DO NOTHING
                RETURNING event_id, execution_id, organization_id, project_id,
                          event_type, sequence_number, occurred_at, received_at,
                          late_for_runtime_findings, runtime_findings_finalization_cutoff_at, runtime_findings_lateness_policy_hours,
                          correlation_id, causation_id, actor_id, actor_type,
                          step_id, step_name, step_lifecycle, parent_step_id, source_kind,
                          resource_references_json, evidence_references_json,
                          attributes_json, event_schema_version, idempotency_key,
                          created_at
                """,
                {
                    "event_id": event.event_id,
                    "execution_id": event.execution_id,
                    "organization_id": event.organization_id,
                    "project_id": event.project_id or "",
                    "event_type": event.event_type.value,
                    "sequence_number": event.sequence_number,
                    "occurred_at": event.occurred_at,
                    "received_at": event.received_at,
                    "late_for_runtime_findings": event.late_for_runtime_findings,
                    "runtime_findings_finalization_cutoff_at": event.runtime_findings_finalization_cutoff_at,
                    "runtime_findings_lateness_policy_hours": event.runtime_findings_lateness_policy_hours,
                    "correlation_id": event.correlation_id,
                    "causation_id": event.causation_id,
                    "actor_id": event.actor_id,
                    "actor_type": event.actor_type.value if event.actor_type else None,
                    "step_id": event.workflow_step.step_id if event.workflow_step else None,
                    "step_name": event.workflow_step.step_name if event.workflow_step else None,
                    "step_lifecycle": (
                        event.workflow_step.lifecycle.value
                        if event.workflow_step
                        else None
                    ),
                    "parent_step_id": (
                        event.workflow_step.parent_step_id
                        if event.workflow_step
                        else None
                    ),
                    "source_kind": (
                        event.workflow_step.source_kind if event.workflow_step else None
                    ),
                    "resource_references_json": json.dumps(
                        list(event.resource_references),
                        separators=(",", ":"),
                    ),
                    "evidence_references_json": json.dumps(
                        list(event.evidence_references),
                        separators=(",", ":"),
                    ),
                    "attributes_json": json.dumps(
                        dict(event.attributes),
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ),
                    "event_schema_version": event.event_schema_version,
                    "idempotency_key": idempotency_key,
                    "created_at": event.received_at,
                },
            ).fetchone()
            connection.commit()

        if result is None:
            # Row was not inserted — a concurrent duplicate already holds the
            # idempotency key.  Read it back and compare attributes for conflict
            # detection.
            existing = self.find_by_idempotency_key(
                idempotency_key or "",
                event.execution_id,
                event.organization_id,
                event.project_id,
            )
            if existing is not None and (
                existing.event_type is not event.event_type
                or dict(existing.attributes) != dict(event.attributes)
                or existing.workflow_step != event.workflow_step
            ):
                raise AgentExecutionIdempotencyConflict(
                    f"Idempotency key conflict for execution '{event.execution_id}'."
                )
            # Idempotent replay — return the existing event.
            if existing is not None:
                return existing

        return _event_from_row(result) if result else event

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
                SELECT event_id, execution_id, organization_id, project_id,
                       event_type, sequence_number, occurred_at, received_at,
                       late_for_runtime_findings, runtime_findings_finalization_cutoff_at, runtime_findings_lateness_policy_hours,
                       correlation_id, causation_id, actor_id, actor_type,
                       step_id, step_name, step_lifecycle, parent_step_id, source_kind,
                       resource_references_json, evidence_references_json,
                       attributes_json, event_schema_version, idempotency_key,
                       created_at
                FROM agent_execution_event
                WHERE organization_id=%(organization_id)s
                  AND project_id=%(project_id)s
                  AND event_id=%(event_id)s
                  AND execution_id=%(execution_id)s
                """,
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "event_id": event_id,
                    "execution_id": execution_id,
                },
            ).fetchone()
        if row is None:
            return None
        return _event_from_row(row)

    def list_by_execution(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
        filters: AgentExecutionEventListFilters | None = None,
    ) -> list[AgentExecutionEvent]:
        conditions = [
            "organization_id=%(organization_id)s",
            "project_id=%(project_id)s",
            "execution_id=%(execution_id)s",
        ]
        params: dict = {
            "organization_id": organization_id,
            "project_id": project_id or "",
            "execution_id": execution_id,
        }
        param_counter = 0

        if filters is not None:
            if filters.event_type is not None:
                param_counter += 1
                conditions.append(f"event_type=%(event_type_{param_counter})s")
                params[f"event_type_{param_counter}"] = filters.event_type.value

            if filters.actor_id is not None:
                param_counter += 1
                conditions.append(f"actor_id=%(actor_id_{param_counter})s")
                params[f"actor_id_{param_counter}"] = filters.actor_id

            if filters.occurred_after is not None:
                param_counter += 1
                conditions.append(f"occurred_at>=%(occurred_after_{param_counter})s")
                params[f"occurred_after_{param_counter}"] = filters.occurred_after

            if filters.occurred_before is not None:
                param_counter += 1
                conditions.append(f"occurred_at<=%(occurred_before_{param_counter})s")
                params[f"occurred_before_{param_counter}"] = filters.occurred_before

        where_clause = " AND ".join(conditions)
        limit = filters.limit if filters else 200

        query = f"""
            SELECT event_id, execution_id, organization_id, project_id,
                   event_type, sequence_number, occurred_at, received_at,
                   late_for_runtime_findings, runtime_findings_finalization_cutoff_at, runtime_findings_lateness_policy_hours,
                   correlation_id, causation_id, actor_id, actor_type,
                   step_id, step_name, step_lifecycle, parent_step_id, source_kind,
                   resource_references_json, evidence_references_json,
                   attributes_json, event_schema_version, idempotency_key,
                   created_at
            FROM agent_execution_event
            WHERE {where_clause}
            ORDER BY sequence_number ASC
            LIMIT %(limit)s
        """
        params["limit"] = limit

        with self._database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_event_from_row(row) for row in rows]

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
                SELECT event_id, execution_id, organization_id, project_id,
                       event_type, sequence_number, occurred_at, received_at,
                       late_for_runtime_findings, runtime_findings_finalization_cutoff_at, runtime_findings_lateness_policy_hours,
                       correlation_id, causation_id, actor_id, actor_type,
                       step_id, step_name, step_lifecycle, parent_step_id, source_kind,
                       resource_references_json, evidence_references_json,
                       attributes_json, event_schema_version, idempotency_key,
                       created_at
                FROM agent_execution_event
                WHERE organization_id=%(organization_id)s
                  AND project_id=%(project_id)s
                  AND execution_id=%(execution_id)s
                  AND idempotency_key=%(idempotency_key)s
                """,
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "execution_id": execution_id,
                    "idempotency_key": idempotency_key,
                },
            ).fetchone()
        if row is None:
            return None
        return _event_from_row(row)

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
                WHERE organization_id=%(organization_id)s
                  AND project_id=%(project_id)s
                  AND execution_id=%(execution_id)s
                """,
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "execution_id": execution_id,
                },
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
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        correlation_id=row["correlation_id"],
        parent_execution_id=row["parent_execution_id"],
        metadata=json.loads(row["metadata_json"]) if row.get("metadata_json") else {},
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _event_from_row(row: dict) -> AgentExecutionEvent:
    return AgentExecutionEvent(
        event_id=row["event_id"],
        execution_id=row["execution_id"],
        organization_id=row["organization_id"],
        project_id=row["project_id"] or None,
        event_type=EventType(row["event_type"]),
        sequence_number=row["sequence_number"],
        occurred_at=row["occurred_at"],
        received_at=row["received_at"],
        late_for_runtime_findings=bool(row.get("late_for_runtime_findings", False)),
        runtime_findings_finalization_cutoff_at=row.get("runtime_findings_finalization_cutoff_at"),
        runtime_findings_lateness_policy_hours=row.get("runtime_findings_lateness_policy_hours"),
        correlation_id=row["correlation_id"],
        causation_id=row["causation_id"],
        actor_id=row["actor_id"],
        actor_type=ActorType(row["actor_type"]) if row.get("actor_type") else None,
        workflow_step=_workflow_step_from_row(row),
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
