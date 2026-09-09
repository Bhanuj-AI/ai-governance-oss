"""Hard, fail-closed deadline enforcement for worker-owned provider calls."""

from __future__ import annotations

import signal
from collections.abc import Callable
from threading import current_thread, main_thread
from typing import TypeVar

Result = TypeVar("Result")


class ExecutionDeadlineExceeded(TimeoutError):
    """Raised when a provider call exceeds its worker-enforced deadline."""


class ExecutionDeadlineUnavailable(RuntimeError):
    """Raised rather than running an allegedly bounded call without a guard."""


class WorkerExecutionDeadline:
    """Interrupt a synchronous provider call in the worker's main thread.

    The replay worker runs handlers on its main thread in a Unix process, where
    ``SIGALRM`` interrupts a blocked provider call. Calls with a configured
    deadline fail closed if that execution model is unavailable; silently
    falling back to an unbounded call would violate the runner contract.
    """

    def call(
        self,
        timeout_seconds: int | None,
        operation: Callable[[], Result],
    ) -> Result:
        if timeout_seconds is None:
            return operation()
        if timeout_seconds <= 0:
            raise ValueError("Execution deadline must be greater than zero.")
        if not hasattr(signal, "SIGALRM") or current_thread() is not main_thread():
            raise ExecutionDeadlineUnavailable(
                "A bounded provider call requires the worker main thread with SIGALRM support."
            )

        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_timer = signal.setitimer(signal.ITIMER_REAL, 0)

        def _timeout_handler(_signum: int, _frame: object) -> None:
            raise ExecutionDeadlineExceeded(
                f"Provider execution exceeded the hard worker deadline of {timeout_seconds} seconds."
            )

        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            return operation()
        finally:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)
            signal.signal(signal.SIGALRM, previous_handler)
