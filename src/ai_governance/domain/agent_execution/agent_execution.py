"""AgentExecution aggregate for externally executed agent runs.

An AgentExecution represents one externally executed agent run that the
AI Governance Platform observes, records, and makes auditable. The platform
does not execute agents; it ingests events from external runtimes and
maintains a deterministic, immutable record.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any


class AgentExecutionStatus(str, Enum):
    """Lifecycle states for an agent execution trace."""

    RECEIVED = "RECEIVED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_TERMINAL_STATES = frozenset(
    {
        AgentExecutionStatus.SUCCEEDED,
        AgentExecutionStatus.FAILED,
        AgentExecutionStatus.CANCELLED,
    }
)


@dataclass(frozen=True)
class AgentExecution:
    """A durable, tenant-scoped record of one externally executed agent run.

    Attributes:
        execution_id: AI Governance Platform-owned unique identifier.
        tenant_id: Deprecated alias for organization_id; use that instead.
        organization_id: Tenant organization scope.
        project_id: Tenant project scope (may be None).
        agent_id: Identifier for the agent definition.
        agent_name: Human-readable agent name.
        agent_version: Agent version string.
        external_execution_id: Runtime-owned execution identifier.
        runtime_provider: External runtime provider name.
        status: Current lifecycle state.
        started_at: When the execution began.
        completed_at: Set only for terminal states; immutable once set.
        correlation_id: Optional cross-cutting correlation identifier.
        parent_execution_id: Optional parent execution reference.
        created_at: Platform-assigned creation timestamp.
        updated_at: Platform-assigned last-modified timestamp.
        metadata: Bounded, JSON-safe execution metadata.
        version: Optimistic concurrency version counter.
    """

    execution_id: str
    organization_id: str
    project_id: str | None
    agent_id: str
    agent_name: str
    agent_version: str
    external_execution_id: str
    runtime_provider: str
    status: AgentExecutionStatus
    started_at: datetime
    completed_at: datetime | None
    correlation_id: str | None
    parent_execution_id: str | None
    created_at: datetime
    updated_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: int = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("execution_id", self.execution_id),
            ("organization_id", self.organization_id),
            ("agent_id", self.agent_id),
            ("agent_name", self.agent_name),
            ("agent_version", self.agent_version),
            ("external_execution_id", self.external_execution_id),
            ("runtime_provider", self.runtime_provider),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty.")
        if self.project_id is not None and not self.project_id.strip():
            raise ValueError("project_id must not be blank.")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at.")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at.")
        if self.version < 0:
            raise ValueError("version must be non-negative.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    # -- Lifecycle transitions ------------------------------------------------

    def mark_running(self, now: datetime) -> AgentExecution:
        """Transition from RECEIVED to RUNNING."""
        if self.status is not AgentExecutionStatus.RECEIVED:
            raise ValueError(
                f"Cannot transition to RUNNING from {self.status.value} state."
            )
        return replace(
            self,
            status=AgentExecutionStatus.RUNNING,
            updated_at=now,
        )

    def mark_terminal(self, status: AgentExecutionStatus, now: datetime) -> AgentExecution:
        """Transition to a terminal state (SUCCEEDED, FAILED, CANCELLED).

        Once terminal, the execution is immutable.
        """
        if status not in _TERMINAL_STATES:
            raise ValueError(f"{status.value} is not a terminal state.")
        if self.status in _TERMINAL_STATES:
            raise ValueError(
                f"Execution is already terminal ({self.status.value}); "
                "terminal states are immutable."
            )
        if self.completed_at is not None:
            raise ValueError(
                "completed_at is already set; execution is terminal."
            )
        return replace(
            self,
            status=status,
            completed_at=now,
            updated_at=now,
        )

    def bump_version(self, now: datetime) -> AgentExecution:
        """Increment the optimistic concurrency version."""
        return replace(
            self,
            version=self.version + 1,
            updated_at=now,
        )

    # -- Read helpers ---------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATES

    @property
    def duration_seconds(self) -> float | None:
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()
