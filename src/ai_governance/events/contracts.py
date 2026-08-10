"""Versioned public domain event contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from uuid import uuid4

from ai_governance.spi.context import TenantContext


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Base class for a versioned, immutable in-process domain event.

    Producers must pass tenant context explicitly. ``event_id`` supports
    idempotency and ``correlation_id`` connects diagnostics across a workflow.
    The contract version belongs to the event schema, allowing a new event type
    to be introduced without changing existing subscribers.
    """

    tenant: TenantContext
    correlation_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    contract_version: str = "v1"

    def __post_init__(self) -> None:
        """Copy and freeze top-level tenant context before publication."""
        object.__setattr__(self, "tenant", MappingProxyType(dict(self.tenant)))


@dataclass(frozen=True, kw_only=True)
class TransactionalDomainEvent(DomainEvent):
    """A generic event whose publication is coordinated with a database transaction.

    The payload stays application-owned; a plugin may persist its own durable
    projection in the same transaction without adding product semantics to OSS.
    """

    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, kw_only=True)
class ResourceLifecycleEvent(TransactionalDomainEvent):
    """Generic immutable fact that a tenant-scoped resource reached a lifecycle state.

    The resource kind and state are deliberately data, not Core enums, so
    independent plugins can consume the same stable event contract.
    """

    resource_kind: str
    resource_id: str
    state: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if not all(value.strip() for value in (self.resource_kind, self.resource_id, self.state)):
            raise ValueError("resource_kind, resource_id, and state are required.")


@dataclass(frozen=True, kw_only=True)
class EvaluationCompleted(DomainEvent):
    """Published when an evaluation result has been finalized by its producer.

    Subscribers may perform non-invasive work such as intelligence analysis,
    external governance synchronization, or usage metering. They must treat
    ``result`` as immutable and honor the tenant carried by the event.
    """
    evaluation_id: str
    result: Mapping[str, object]

    def __post_init__(self) -> None:
        """Freeze the top-level result payload in addition to base context."""
        super().__post_init__()
        object.__setattr__(self, "result", MappingProxyType(dict(self.result)))


@dataclass(frozen=True, kw_only=True)
class ExecutionCompleted(DomainEvent):
    """Published when a governed workflow execution reaches its final result."""
    execution_id: str
    result: Mapping[str, object]

    def __post_init__(self) -> None:
        """Freeze the top-level result payload in addition to base context."""
        super().__post_init__()
        object.__setattr__(self, "result", MappingProxyType(dict(self.result)))
