"""Repository interfaces for agent execution traces.

AgentExecutionRepository manages the AgentExecution aggregate lifecycle.
AgentExecutionEventRepository manages append-only event persistence with
idempotency guarantees.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
)


@dataclass(frozen=True)
class AgentExecutionListFilters:
    """Filters for listing agent executions."""

    agent_id: str | None = None
    status: AgentExecutionStatus | None = None
    runtime_provider: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 100


@dataclass(frozen=True)
class AgentExecutionAgentListFilters:
    """Paging controls for the tenant-scoped agent index."""

    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class AgentExecutionAgentSummary:
    """Aggregated execution evidence for one observed agent."""

    agent_id: str
    agent_name: str
    runtime_provider: str
    execution_count: int
    succeeded_count: int
    failed_count: int
    running_count: int
    last_started_at: datetime


@dataclass(frozen=True)
class AgentExecutionEventListFilters:
    """Filters for listing events within an execution."""

    event_type: EventType | None = None
    actor_id: str | None = None
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None
    limit: int = 200


class AgentExecutionRepository(ABC):
    """Tenant-scoped persistence boundary for AgentExecution aggregates."""

    @abstractmethod
    def save(self, execution: AgentExecution) -> AgentExecution:
        """Save or update an agent execution.

        Returns the persisted execution with updated version/timestamps.
        """

    @abstractmethod
    def get(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecution | None:
        """Retrieve one execution by its platform-owned ID."""

    @abstractmethod
    def get_by_external_id(
        self,
        external_execution_id: str,
        runtime_provider: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecution | None:
        """Retrieve one execution by its runtime-owned external ID."""

    @abstractmethod
    def list(
        self,
        filters: AgentExecutionListFilters,
        organization_id: str,
        project_id: str | None = None,
    ) -> list[AgentExecution]:
        """List executions matching the given filters."""

    @abstractmethod
    def list_agents(
        self,
        filters: AgentExecutionAgentListFilters,
        organization_id: str,
        project_id: str | None = None,
    ) -> list[AgentExecutionAgentSummary]:
        """List observed agents with deterministic aggregated execution evidence."""

    @abstractmethod
    def update_status(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None,
        new_status: AgentExecutionStatus,
        completed_at: datetime | None,
        expected_version: int,
    ) -> AgentExecution:
        """Atomically update status with optimistic concurrency control."""


class AgentExecutionEventRepository(ABC):
    """Tenant-scoped persistence boundary for append-only execution events."""

    @abstractmethod
    def save(
        self,
        event: AgentExecutionEvent,
        idempotency_key: str | None = None,
    ) -> AgentExecutionEvent:
        """Persist an event. Returns the persisted event.

        If idempotency_key is provided, duplicate delivery with the same key
        and identical payload is a no-op; conflicting payloads raise
        AgentExecutionIdempotencyConflict.
        """

    @abstractmethod
    def get_by_id(
        self,
        event_id: str,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecutionEvent | None:
        """Retrieve one event by its ID within an execution."""

    @abstractmethod
    def list_by_execution(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
        filters: AgentExecutionEventListFilters | None = None,
    ) -> list[AgentExecutionEvent]:
        """List events for an execution, ordered by sequence_number ASC."""

    @abstractmethod
    def find_by_idempotency_key(
        self,
        idempotency_key: str,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> AgentExecutionEvent | None:
        """Find a previously ingested event by its idempotency key."""

    @abstractmethod
    def max_sequence_number(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> int:
        """Return the highest sequence_number for an execution."""
