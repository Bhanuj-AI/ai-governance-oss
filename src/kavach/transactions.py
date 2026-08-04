"""Generic shared database transaction contracts for extension participation."""

from __future__ import annotations

from typing import Any, Protocol


class TransactionContext(Protocol):
    """An open database transaction that participating repositories can reuse.

    The context owns neither domain semantics nor plugin behavior. A caller
    starts it through the owning repository, performs all participating writes
    against ``connection``, then commits or rolls back the complete unit.
    """

    connection: Any

    def commit(self) -> None:
        """Commit every write performed through the shared connection."""

    def rollback(self) -> None:
        """Roll back every write performed through the shared connection."""


class ConnectionTransactionContext:
    """Minimal transaction-context implementation around one DB-API connection."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self._finished = False

    def commit(self) -> None:
        """Commit once; repeated calls are intentionally harmless."""
        if not self._finished:
            self.connection.commit()
            self._finished = True

    def rollback(self) -> None:
        """Roll back once; repeated calls are intentionally harmless."""
        if not self._finished:
            self.connection.rollback()
            self._finished = True
