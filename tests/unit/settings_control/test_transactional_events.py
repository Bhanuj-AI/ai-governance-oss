"""Unit coverage for generic transaction-aware settings event publication."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from ai_governance.events import EventPublisher, ResourceLifecycleEvent
from ai_governance.hooks.contracts import FailurePolicy
from ai_governance.settings_control.domain import SettingContext, SettingScope
from ai_governance.settings_control.repository import InMemorySettingsRepository
from ai_governance.settings_control.service import ConfigurationService


class _Transaction:
    """Small transaction double used to prove caller-owned commit semantics."""

    connection = object()

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class TransactionalInMemorySettingsRepository(InMemorySettingsRepository):
    """In-memory rollback model used only to test the public transaction flow."""

    @contextmanager
    def transaction(self):
        values, audit = self._values.copy(), self._audit.copy()
        transaction = _Transaction()
        try:
            yield transaction
        except Exception:
            self._values, self._audit = values, audit
            transaction.rollback()
            raise
        else:
            transaction.commit()


def test_transactional_settings_event_is_redacted_and_commits_with_mutation() -> None:
    """A transaction-aware subscriber receives the same open context as save."""
    repository = TransactionalInMemorySettingsRepository()
    publisher = EventPublisher()
    received: list[tuple[ResourceLifecycleEvent, _Transaction]] = []
    publisher.subscribe(
        event_type=ResourceLifecycleEvent,
        handler=lambda event, transaction: received.append((event, transaction)),
        plugin_name="transaction-test",
        failure_policy=FailurePolicy.FAIL_CLOSED,
    )

    ConfigurationService(repository, {}, publisher).update(
        "mcp.dry_run_default",
        True,
        "actor-1",
        "safe update",
        0,
        SettingScope.PROJECT,
        SettingContext("org-1", "project-1"),
    )

    event, transaction = received[0]
    assert repository.get("mcp.dry_run_default", SettingScope.PROJECT, "project-1")
    assert transaction.committed and not transaction.rolled_back
    assert event.payload["key"] == "mcp.dry_run_default"
    assert "value" not in event.payload
    assert event.payload["sensitive"] is False


def test_transactional_event_failure_rolls_back_the_business_mutation() -> None:
    """A fail-closed extension insertion failure aborts the owning transaction."""
    repository = TransactionalInMemorySettingsRepository()
    publisher = EventPublisher()

    def fail(event: ResourceLifecycleEvent, transaction: _Transaction) -> None:
        raise RuntimeError("outbox unavailable")

    publisher.subscribe(
        event_type=ResourceLifecycleEvent,
        handler=fail,
        plugin_name="failing-transaction-test",
        failure_policy=FailurePolicy.FAIL_CLOSED,
    )
    service = ConfigurationService(repository, {}, publisher)

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        service.update("mcp.dry_run_default", True, "actor-1", "safe update", 0)

    assert repository.get("mcp.dry_run_default", SettingScope.SYSTEM, "") is None


def test_non_transactional_repository_still_publishes_standalone_event() -> None:
    """SQLite and in-memory settings retain standalone event publication behavior."""
    publisher = EventPublisher()
    received: list[ResourceLifecycleEvent] = []
    publisher.subscribe(
        event_type=ResourceLifecycleEvent,
        handler=received.append,
        plugin_name="standalone-test",
    )
    ConfigurationService(InMemorySettingsRepository(), {}, publisher).update(
        "mcp.dry_run_default", True, "actor-1", "safe update", 0
    )

    assert received[0].state == "changed"
