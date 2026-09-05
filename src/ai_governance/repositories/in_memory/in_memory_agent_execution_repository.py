"""In-memory AgentExecutionRepository for tests and local workflows."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from threading import Lock

from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
)
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


class InMemoryAgentExecutionRepository(AgentExecutionRepository):
    """In-memory store for AgentExecution aggregates."""

    def __init__(self) -> None:
        self._executions_by_id: dict[str, AgentExecution] = {}
        self._executions_by_external: dict[tuple[str, str], str] = {}
        self._lock = Lock()

    def save(self, execution: AgentExecution) -> AgentExecution:
        with self._lock:
            self._executions_by_id[execution.execution_id] = execution
            key = (execution.external_execution_id, execution.runtime_provider)
            self._executions_by_external[key] = execution.execution_id
        return execution

    def get(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecution | None:
        execution = self._executions_by_id.get(execution_id)
        if execution is None:
            return None
        if execution.organization_id != organization_id:
            return None
        if project_id is not None and execution.project_id != project_id:
            return None
        return execution

    def get_by_external_id(
        self,
        external_execution_id: str,
        runtime_provider: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecution | None:
        key = (external_execution_id, runtime_provider)
        execution_id = self._executions_by_external.get(key)
        if execution_id is None:
            return None
        return self.get(execution_id, organization_id, project_id)

    def list(
        self,
        filters: AgentExecutionListFilters,
        organization_id: str,
        project_id: str | None = None,
    ) -> list[AgentExecution]:
        results = []
        for execution in self._executions_by_id.values():
            if execution.organization_id != organization_id:
                continue
            if project_id is not None and execution.project_id != project_id:
                continue
            if filters.agent_id is not None and execution.agent_id != filters.agent_id:
                continue
            if filters.status is not None and execution.status != filters.status:
                continue
            if filters.runtime_provider is not None and execution.runtime_provider != filters.runtime_provider:
                continue
            if filters.created_after is not None and execution.created_at < filters.created_after:
                continue
            if filters.created_before is not None and execution.created_at > filters.created_before:
                continue
            results.append(execution)
        return sorted(results, key=lambda e: (e.created_at, e.execution_id))[: filters.limit]

    def list_agents(
        self,
        filters: AgentExecutionAgentListFilters,
        organization_id: str,
        project_id: str | None = None,
    ) -> list[AgentExecutionAgentSummary]:
        aggregates: dict[tuple[str, str, str], dict[str, object]] = {}
        for execution in self._executions_by_id.values():
            if execution.organization_id != organization_id:
                continue
            if project_id is not None and execution.project_id != project_id:
                continue
            key = (execution.agent_id, execution.agent_name, execution.runtime_provider)
            aggregate = aggregates.setdefault(
                key,
                {
                    "execution_count": 0,
                    "succeeded_count": 0,
                    "failed_count": 0,
                    "running_count": 0,
                    "last_started_at": execution.started_at,
                },
            )
            aggregate["execution_count"] = int(aggregate["execution_count"]) + 1
            if execution.status is AgentExecutionStatus.SUCCEEDED:
                aggregate["succeeded_count"] = int(aggregate["succeeded_count"]) + 1
            elif execution.status is AgentExecutionStatus.FAILED:
                aggregate["failed_count"] = int(aggregate["failed_count"]) + 1
            elif execution.status is AgentExecutionStatus.RUNNING:
                aggregate["running_count"] = int(aggregate["running_count"]) + 1
            aggregate["last_started_at"] = max(aggregate["last_started_at"], execution.started_at)

        items = [
            AgentExecutionAgentSummary(
                agent_id=agent_id,
                agent_name=agent_name,
                runtime_provider=runtime_provider,
                execution_count=int(values["execution_count"]),
                succeeded_count=int(values["succeeded_count"]),
                failed_count=int(values["failed_count"]),
                running_count=int(values["running_count"]),
                last_started_at=values["last_started_at"],  # type: ignore[arg-type]
            )
            for (agent_id, agent_name, runtime_provider), values in aggregates.items()
        ]
        items.sort(
            key=lambda item: (
                -item.last_started_at.timestamp(),
                item.agent_id,
                item.runtime_provider,
            )
        )
        return items[filters.offset : filters.offset + filters.limit]

    def update_status(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None,
        new_status: AgentExecutionStatus,
        completed_at: datetime | None,
        expected_version: int,
    ) -> AgentExecution:
        with self._lock:
            execution = self._executions_by_id.get(execution_id)
            if execution is None:
                raise ValueError(f"Execution '{execution_id}' not found.")
            if execution.organization_id != organization_id:
                raise ValueError("Organization mismatch.")
            if project_id is not None and execution.project_id != project_id:
                raise ValueError("Project mismatch.")
            if execution.version != expected_version:
                raise AgentExecutionConcurrencyConflict(
                    f"Version mismatch: expected {expected_version}, got {execution.version}."
                )
            updated = replace(
                execution,
                status=new_status,
                completed_at=completed_at,
                version=execution.version + 1,
            )
            self._executions_by_id[execution_id] = updated
            return updated


class InMemoryAgentExecutionEventRepository(AgentExecutionEventRepository):
    """In-memory store for append-only AgentExecutionEvents."""

    def __init__(self) -> None:
        self._events_by_id: dict[str, AgentExecutionEvent] = {}
        self._events_by_execution: dict[str, list[AgentExecutionEvent]] = {}
        self._events_by_idempotency: dict[tuple[str, str], AgentExecutionEvent] = {}
        self._lock = Lock()

    def save(
        self,
        event: AgentExecutionEvent,
        idempotency_key: str | None = None,
    ) -> AgentExecutionEvent:
        with self._lock:
            if idempotency_key is not None:
                existing = self._events_by_idempotency.get(
                    (idempotency_key, event.execution_id)
                )
                if existing is not None:
                    # Compare attributes for conflict detection.
                    if dict(existing.attributes) != dict(event.attributes):
                        raise AgentExecutionIdempotencyConflict(
                            f"Idempotency key '{idempotency_key}' reused with "
                            f"different payload for execution '{event.execution_id}'."
                        )
                    return existing

            self._events_by_id[event.event_id] = event
            exec_events = self._events_by_execution.setdefault(
                event.execution_id, []
            )
            # Avoid duplicates by event_id.
            if not any(e.event_id == event.event_id for e in exec_events):
                exec_events.append(event)
                exec_events.sort(key=lambda e: e.sequence_number)

            if idempotency_key is not None:
                self._events_by_idempotency[
                    (idempotency_key, event.execution_id)
                ] = event

            return event

    def get_by_id(
        self,
        event_id: str,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecutionEvent | None:
        event = self._events_by_id.get(event_id)
        if event is None or event.execution_id != execution_id:
            return None
        if event.organization_id != organization_id:
            return None
        if project_id is not None and event.project_id != project_id:
            return None
        return event

    def list_by_execution(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
        filters: AgentExecutionEventListFilters | None = None,
    ) -> list[AgentExecutionEvent]:
        events = self._events_by_execution.get(execution_id, [])
        results = []
        for event in events:
            if event.organization_id != organization_id:
                continue
            if project_id is not None and event.project_id != project_id:
                continue
            if filters is not None:
                if filters.event_type is not None and event.event_type != filters.event_type:
                    continue
                if filters.actor_id is not None and event.actor_id != filters.actor_id:
                    continue
                if filters.occurred_after is not None and event.occurred_at < filters.occurred_after:
                    continue
                if filters.occurred_before is not None and event.occurred_at > filters.occurred_before:
                    continue
            results.append(event)
        return results[: (filters.limit if filters else 200)]

    def find_by_idempotency_key(
        self,
        idempotency_key: str,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecutionEvent | None:
        event = self._events_by_idempotency.get(
            (idempotency_key, execution_id)
        )
        if event is None:
            return None
        if event.organization_id != organization_id:
            return None
        if project_id is not None and event.project_id != project_id:
            return None
        return event

    def max_sequence_number(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> int:
        events = self._events_by_execution.get(execution_id, [])
        max_seq = 0
        for event in events:
            if event.organization_id != organization_id:
                continue
            if project_id is not None and event.project_id != project_id:
                continue
            max_seq = max(max_seq, event.sequence_number)
        return max_seq
