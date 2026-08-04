"""Execution registry for ordered lifecycle hooks."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections import defaultdict
from collections.abc import Awaitable

from kavach.hooks.contracts import (
    FailurePolicy,
    HookDefinition,
    HookExecution,
    HookHandler,
    HookInvocation,
)


class HookRegistrationError(RuntimeError):
    """Raised for invalid timeout/retry configuration or duplicate ownership."""


class HookExecutionError(RuntimeError):
    """Raised after a hook with ``FAIL_CLOSED`` exhausts its attempts."""


class HookRegistry:
    """Run named lifecycle hooks in deterministic order with declared failure policy.

    The registry supports synchronous and asynchronous handlers. It sorts by
    ``(order, registration sequence)`` and records a bounded recent-execution
    view for diagnostics. Hooks are process-local; durable retries or
    dead-letter persistence belong to a future worker-backed implementation.
    """
    def __init__(self) -> None:
        self._hooks: dict[str, list[HookDefinition]] = defaultdict(list)
        self._sequence = 0
        self._executions: list[HookExecution] = []

    def register(
        self,
        *,
        name: str,
        handler: HookHandler,
        plugin_name: str,
        order: int = 100,
        failure_policy: FailurePolicy = FailurePolicy.FAIL_CLOSED,
        timeout_seconds: float | None = None,
        retries: int = 0,
    ) -> None:
        """Register one plugin handler for a named extension point.

        A plugin can own a hook name only once, preventing duplicate execution
        caused by reloads or repeated registration. ``retries`` counts retries
        after the initial attempt; a timeout applies only to awaitable handlers.
        """
        if retries < 0 or timeout_seconds is not None and timeout_seconds <= 0:
            raise HookRegistrationError("Hook retries and timeout must be non-negative.")
        if any(item.plugin_name == plugin_name for item in self._hooks[name]):
            raise HookRegistrationError(
                f"Plugin '{plugin_name}' already registered hook '{name}'."
            )
        self._sequence += 1
        self._hooks[name].append(
            HookDefinition(
                name=name, handler=handler, plugin_name=plugin_name, order=order,
                failure_policy=failure_policy, timeout_seconds=timeout_seconds,
                retries=retries, sequence=self._sequence,
            )
        )
        self._hooks[name].sort(key=lambda item: (item.order, item.sequence))

    async def invoke(self, invocation: HookInvocation) -> tuple[HookExecution, ...]:
        """Invoke all handlers for ``invocation.name`` in deterministic order.

        Results are returned and retained for diagnostics. A failed
        ``FAIL_CLOSED`` handler raises :class:`HookExecutionError` immediately
        after its result is recorded; all other declared policies isolate the
        failure and allow later handlers to run.
        """
        results: list[HookExecution] = []
        for definition in self._hooks.get(invocation.name, ()):
            execution = await self._invoke_one(definition, invocation)
            results.append(execution)
            self._executions.append(execution)
            if execution.outcome == "failed" and definition.failure_policy == FailurePolicy.FAIL_CLOSED:
                raise HookExecutionError(
                    f"Hook '{definition.name}' from '{definition.plugin_name}' failed: "
                    f"{execution.failure_reason}"
                )
        return tuple(results)

    def diagnostics(self) -> dict[str, object]:
        """Return registered policy plus the latest 100 execution outcomes."""
        return {
            "registered": [
                {
                    "name": item.name, "plugin": item.plugin_name, "order": item.order,
                    "failure_policy": item.failure_policy.value,
                    "timeout_seconds": item.timeout_seconds, "retries": item.retries,
                }
                for name in sorted(self._hooks)
                for item in self._hooks[name]
            ],
            "recent_executions": [
                {
                    "hook": item.hook_name, "plugin": item.plugin_name,
                    "order": item.order, "outcome": item.outcome,
                    "duration_ms": item.duration_ms, "failure_reason": item.failure_reason,
                }
                for item in self._executions[-100:]
            ],
        }

    async def _invoke_one(
        self, definition: HookDefinition, invocation: HookInvocation
    ) -> HookExecution:
        """Execute one handler, applying its retry and timeout declaration."""
        started = time.perf_counter()
        failure: Exception | None = None
        attempts = definition.retries + 1
        for _ in range(attempts):
            try:
                result = definition.handler(invocation)
                if inspect.isawaitable(result):
                    await _await_with_timeout(result, definition.timeout_seconds)
                return HookExecution(
                    plugin_name=definition.plugin_name, hook_name=definition.name,
                    order=definition.order, outcome="succeeded",
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
            except Exception as exc:
                failure = exc
        return HookExecution(
            plugin_name=definition.plugin_name, hook_name=definition.name,
            order=definition.order, outcome="failed",
            duration_ms=(time.perf_counter() - started) * 1000,
            failure_reason=str(failure),
        )


async def _await_with_timeout(
    awaitable: Awaitable[object], timeout_seconds: float | None
) -> object:
    """Await a handler result with an optional per-attempt timeout."""
    if timeout_seconds is None:
        return await awaitable
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
