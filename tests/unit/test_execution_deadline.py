from __future__ import annotations

from threading import Thread
from time import sleep

import pytest

from ai_governance.services.execution_deadline import (
    ExecutionDeadlineExceeded,
    ExecutionDeadlineUnavailable,
    WorkerExecutionDeadline,
)


def test_worker_execution_deadline_interrupts_a_blocking_provider_call() -> None:
    deadline = WorkerExecutionDeadline()

    with pytest.raises(ExecutionDeadlineExceeded, match="hard worker deadline"):
        deadline.call(1, lambda: sleep(2))


def test_worker_execution_deadline_fails_closed_outside_worker_main_thread() -> None:
    failures: list[Exception] = []

    def run_in_thread() -> None:
        try:
            WorkerExecutionDeadline().call(1, lambda: None)
        except Exception as exc:  # noqa: BLE001 - The test records the fail-closed outcome.
            failures.append(exc)

    thread = Thread(target=run_in_thread)
    thread.start()
    thread.join()

    assert len(failures) == 1
    assert isinstance(failures[0], ExecutionDeadlineUnavailable)
