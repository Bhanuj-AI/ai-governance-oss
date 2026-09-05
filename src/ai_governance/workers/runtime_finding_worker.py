"""Worker for deterministic runtime finding detection.

Uses the existing job/worker infrastructure. Detection is idempotent
and failure-isolated: one detector failure does not prevent others
from running.
"""

from __future__ import annotations

import signal
import socket
from threading import Event

from ai_governance.services.runtime_finding_service import RuntimeFindingService


class RuntimeFindingWorkerRuntime:
    def __init__(self, worker) -> None:
        self._worker = worker
        self._stop_event = Event()

    def stop(self, *_args) -> None:
        self._stop_event.set()

    def run_forever(self) -> None:
        self._worker.run_forever(self._stop_event)


def create_runtime_finding_worker_runtime(*, worker_id: str | None = None):
    """Build a runtime finding worker from the same repository dependencies."""
    from ai_governance.api.dependencies.repositories import (
        get_agent_execution_repository,
    )
    from ai_governance.domain.runtime_findings.detectors import ALL_DETECTORS
    from ai_governance.repositories.factories import (
        RuntimeFindingRepositoryFactory,
    )
    from ai_governance.services.runtime_aggregation_service import (
        RuntimeAggregationService,
    )
    from ai_governance.services.runtime_finding_service import (
        RuntimeFindingService,
    )
    from ai_governance.settings import load_settings

    settings = load_settings()
    finding_repo = RuntimeFindingRepositoryFactory(settings).create()

    exec_repo = get_agent_execution_repository()
    aggregation_service = RuntimeAggregationService(
        exec_repo.execution,
        exec_repo.event,
    )

    detectors = tuple(cls() for cls in ALL_DETECTORS)

    finding_service = RuntimeFindingService(
        aggregation_service,
        finding_repo,
        detectors,
    )

    return RuntimeFindingWorkerRuntime(
        _RuntimeFindingWorker(finding_service, worker_id=worker_id or f"finding-{socket.gethostname()}")
    )


def main() -> None:
    runtime = create_runtime_finding_worker_runtime()
    signal.signal(signal.SIGINT, runtime.stop)
    signal.signal(signal.SIGTERM, runtime.stop)
    runtime.run_forever()


# -- Internal worker implementation -------------------------------------------


class _RuntimeFindingWorker:
    """Background worker that runs detection cycles."""

    def __init__(self, service: RuntimeFindingService, worker_id: str) -> None:
        self._service = service
        self._worker_id = worker_id
        self._poll_seconds = 300  # 5 minutes

    def run_forever(self, stop_event: Event) -> None:
        """Poll for detection cycles."""
        import time

        while not stop_event.is_set():
            try:
                self._detection_cycle()
            except Exception:  # noqa: BLE001 - worker retries on its next polling cycle.
                time.sleep(self._poll_seconds)
            stop_event.wait(self._poll_seconds)

    def _detection_cycle(self) -> None:
        """Run detection for all tenants."""
        # In production, this would iterate over known organizations.
        # For now, run a single cycle as a demonstration.
        self._service.run_detection("org_default")


if __name__ == "__main__":
    main()
