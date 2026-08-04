"""In-process, ordered event subscription for extension reactions."""

from __future__ import annotations

import inspect
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from kavach.events.contracts import DomainEvent
from kavach.hooks.contracts import FailurePolicy
from kavach.transactions import TransactionContext

EventT = TypeVar("EventT", bound=DomainEvent)


@dataclass(frozen=True)
class EventSubscription:
    """One ordered plugin reaction to a specific public event type."""
    event_type: type[DomainEvent]
    handler: Callable[..., Any]
    plugin_name: str
    order: int
    failure_policy: FailurePolicy
    sequence: int


class EventPublisher:
    """Publish versioned events to ordered, in-process extension subscribers.

    A subscriber registered for a base event class receives compatible subtype
    events. Subscription order is deterministic: lower ``order`` values run
    first, then registration order. The default failure policy isolates a
    subscriber failure; use ``FAIL_CLOSED`` only when the producing workflow
    must not continue without that extension's successful reaction.
    """
    def __init__(self) -> None:
        self._subscriptions: dict[type[DomainEvent], list[EventSubscription]] = defaultdict(list)
        self._sequence = 0
        self._recent: list[dict[str, object]] = []

    def subscribe(
        self,
        *,
        event_type: type[EventT],
        handler: Callable[[EventT], Any] | Callable[[EventT, TransactionContext], Any],
        plugin_name: str,
        order: int = 100,
        failure_policy: FailurePolicy = FailurePolicy.ISOLATE_AND_CONTINUE,
    ) -> None:
        """Register a single ordered handler for ``event_type`` on one plugin.

        Duplicate ownership for the same plugin and event type is rejected to
        avoid accidental duplicate side effects. A handler may be synchronous
        or return an awaitable.
        """
        if any(item.plugin_name == plugin_name for item in self._subscriptions[event_type]):
            raise ValueError(
                f"Plugin '{plugin_name}' already subscribes to {event_type.__name__}."
            )
        self._sequence += 1
        self._subscriptions[event_type].append(EventSubscription(
            event_type=event_type, handler=cast(Callable[..., Any], handler), plugin_name=plugin_name, order=order,
            failure_policy=failure_policy, sequence=self._sequence,
        ))
        self._subscriptions[event_type].sort(key=lambda item: (item.order, item.sequence))

    async def publish(self, event: DomainEvent) -> None:
        """Deliver ``event`` to compatible subscribers and record each outcome.

        A failure is retained in diagnostics. Only ``FAIL_CLOSED`` re-raises
        the original exception; all other policies allow delivery to continue.
        This publisher does not persist events or retry work across restarts.
        """
        for event_type, subscriptions in self._subscriptions.items():
            if not isinstance(event, event_type):
                continue
            for subscription in subscriptions:
                started = time.perf_counter()
                try:
                    result = subscription.handler(event)
                    if inspect.isawaitable(result):
                        await result
                    outcome, reason = "succeeded", None
                except Exception as exc:
                    outcome, reason = "failed", str(exc)
                    if subscription.failure_policy == FailurePolicy.FAIL_CLOSED:
                        raise
                self._recent.append({
                    "event": type(event).__name__, "plugin": subscription.plugin_name,
                    "order": subscription.order, "outcome": outcome,
                    "duration_ms": (time.perf_counter() - started) * 1000,
                    "failure_reason": reason,
                })

    async def publish_in_transaction(
        self, event: DomainEvent, transaction: TransactionContext
    ) -> None:
        """Publish a generic event while the caller owns an open transaction.

        Handlers that support transaction-aware persistence may accept the
        supplied transaction as their second argument. Legacy one-argument
        handlers remain compatible, so this extends rather than replaces the
        public event SPI.
        """
        for event_type, subscriptions in self._subscriptions.items():
            if not isinstance(event, event_type):
                continue
            for subscription in subscriptions:
                started = time.perf_counter()
                try:
                    parameter_count = len(inspect.signature(subscription.handler).parameters)
                    result = (
                        subscription.handler(event, transaction)
                        if parameter_count >= 2
                        else subscription.handler(event)
                    )
                    if inspect.isawaitable(result):
                        await result
                    outcome, reason = "succeeded", None
                except Exception as exc:
                    outcome, reason = "failed", str(exc)
                    if subscription.failure_policy == FailurePolicy.FAIL_CLOSED:
                        raise
                self._recent.append({
                    "event": type(event).__name__, "plugin": subscription.plugin_name,
                    "order": subscription.order, "outcome": outcome,
                    "duration_ms": (time.perf_counter() - started) * 1000,
                    "failure_reason": reason,
                })

    def diagnostics(self) -> dict[str, object]:
        """Return subscription ownership and the latest 100 publication outcomes."""
        return {
            "subscriptions": [
                {"event": item.event_type.__name__, "plugin": item.plugin_name,
                 "order": item.order, "failure_policy": item.failure_policy.value}
                for event_type in sorted(self._subscriptions, key=lambda item: item.__name__)
                for item in self._subscriptions[event_type]
            ],
            "recent_publications": self._recent[-100:],
        }
