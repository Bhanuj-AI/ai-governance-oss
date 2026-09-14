"""Domain model for external agent execution traces.

This package introduces a first-class, immutable runtime execution record
for externally executed AI agents. AI Governance Platform ingests, validates,
persists, correlates, exposes, and audits execution events emitted by
external runtimes. It does not execute agents or manage agent sessions.
"""

from __future__ import annotations

from ai_governance.domain.agent_execution.agent_execution import (
    AgentExecution,
    AgentExecutionStatus,
)
from ai_governance.domain.agent_execution.agent_execution_event import (
    ActorType,
    AgentExecutionEvent,
    EventType,
    WorkflowStep,
    WorkflowStepLifecycle,
)
from ai_governance.domain.agent_execution.projection import (
    ProjectionStatus,
    ProjectionVersion,
    RuntimeOntologyProjection,
    UnresolvedReference,
)
from ai_governance.domain.agent_execution.replay_capability import (
    AgentRuntimeReplayCapability,
)

__all__ = [
    "ActorType",
    "AgentExecution",
    "AgentExecutionEvent",
    "AgentExecutionStatus",
    "AgentRuntimeReplayCapability",
    "EventType",
    "ProjectionStatus",
    "ProjectionVersion",
    "RuntimeOntologyProjection",
    "UnresolvedReference",
    "WorkflowStep",
    "WorkflowStepLifecycle",
]
