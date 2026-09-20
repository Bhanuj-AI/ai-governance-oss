"""Domain errors for agent execution lifecycle and ingestion."""

from __future__ import annotations


class AgentExecutionError(Exception):
    """Base error for agent execution domain operations."""


class AgentExecutionNotFound(AgentExecutionError):
    """Requested execution was not found in the tenant scope."""


class AgentExecutionInvalidTransition(AgentExecutionError):
    """Lifecycle state transition is not permitted."""


class AgentExecutionTerminalImmutable(AgentExecutionError):
    """Attempted to mutate a terminal-state execution."""


class AgentExecutionIdempotencyConflict(AgentExecutionError):
    """Duplicate event delivery with conflicting payload."""


class AgentExecutionEventNotFound(AgentExecutionError):
    """Requested event was not found within the execution."""


class AgentExecutionRuntimeToolCallConflict(AgentExecutionError):
    """A runtime tool-call ID is already recorded for this execution."""


class AgentExecutionSchemaVersionUnsupported(AgentExecutionError):
    """Event schema version is not supported by this platform version."""


class AgentExecutionPayloadRejected(AgentExecutionError):
    """Event attributes contain prohibited raw payload fields."""


class AgentExecutionUnauthorized(AgentExecutionError):
    """Actor is not authorized for this operation."""


class AgentExecutionConcurrencyConflict(AgentExecutionError):
    """Optimistic concurrency check failed (version mismatch)."""
