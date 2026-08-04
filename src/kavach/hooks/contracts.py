"""Contracts for deterministic, observable workflow hooks."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from kavach.spi.context import TenantContext


class FailurePolicy(StrEnum):
    """Declared behavior when an extension callback cannot complete.

    ``FAIL_CLOSED`` stops the producer by raising after the callback fails.
    The other policies preserve workflow progress; ``RETRY`` controls retry
    attempts and still reports the final failure, while ``DEAD_LETTER`` is an
    observable intent for a durable host integration. The in-process registry
    records all outcomes and currently treats non-closed policies as isolated.
    """
    FAIL_CLOSED = "fail_closed"
    FAIL_OPEN = "fail_open"
    ISOLATE_AND_CONTINUE = "isolate_and_continue"
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"


@dataclass(frozen=True)
class HookInvocation:
    """Immutable input supplied to one named workflow interception point.

    ``payload`` and ``tenant`` are shallow copied into read-only mappings so a
    hook cannot silently replace producer-owned top-level values. Producers
    should therefore pass scalar or immutable nested data and interpret hook
    results through an explicit future mutation contract, rather than sharing
    mutable state with a plugin.
    """

    name: str
    payload: Mapping[str, object]
    tenant: TenantContext
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        """Freeze top-level payload and tenant mappings at the boundary."""
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        object.__setattr__(self, "tenant", MappingProxyType(dict(self.tenant)))


@dataclass(frozen=True)
class HookExecution:
    """Observable outcome of one handler invocation.

    ``order`` is the declared priority, while the registry uses registration
    sequence as a deterministic tie-breaker. Failures are represented as data
    for diagnostics even when a failure policy allows the workflow to proceed.
    """
    plugin_name: str
    hook_name: str
    order: int
    outcome: str
    duration_ms: float
    failure_reason: str | None = None


class HookHandler(Protocol):
    """Synchronous or asynchronous callback accepted by :class:`HookRegistry`.

    Handlers receive immutable input and may return ``None`` or any value; the
    current hook contract intentionally ignores returned values to prohibit
    implicit shared-state mutation.
    """
    def __call__(self, invocation: HookInvocation) -> Any: ...


@dataclass(frozen=True)
class HookDefinition:
    """Immutable registration record defining a hook's execution semantics."""
    name: str
    handler: HookHandler
    plugin_name: str
    order: int = 100
    failure_policy: FailurePolicy = FailurePolicy.FAIL_CLOSED
    timeout_seconds: float | None = None
    retries: int = 0
    sequence: int = field(default=0, compare=False)
