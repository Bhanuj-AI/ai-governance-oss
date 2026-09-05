"""Runnable durable worker for runtime ontology projection.

Runs in the background, picks up pending/failed projections from
Neo4j, and reconciles them against PostgreSQL source data.

If Neo4j is unavailable, the worker retries on the next cycle
without blocking runtime ingestion.
"""

from __future__ import annotations

import signal
import socket
from threading import Event

from ai_governance.services.ontology_projection_service import OntologyProjectionService


class ProjectionWorkerRuntime:
    def __init__(self, worker) -> None:
        self._worker = worker
        self._stop_event = Event()

    def stop(self, *_args) -> None:
        self._stop_event.set()

    def run_forever(self) -> None:
        self._worker.run_forever(self._stop_event)


def create_projection_worker_runtime(*, worker_id: str | None = None):
    """Build a projection worker from the same repository dependencies as the API."""
    from ai_governance.api.dependencies.repositories import (
        get_agent_execution_repository,
    )
    from ai_governance.repositories.neo4j_projection_repository import (
        Neo4jProjectionRepository,
    )
    from ai_governance.services.ontology_projection_service import (
        OntologyProjectionService,
    )

    execution_repo = get_agent_execution_repository()
    event_repo = execution_repo._event_repo if hasattr(execution_repo, "_event_repo") else None

    # The agent execution service wraps both repos; extract them.
    from ai_governance.api.dependencies.agent_execution import (
        get_agent_execution_service,
    )
    service = get_agent_execution_service()
    execution_repo = service._execution_repo
    event_repo = service._event_repo

    projection_repo = Neo4jProjectionRepository.from_environment()
    projection_service = OntologyProjectionService(
        execution_repo, event_repo, projection_repo
    )

    return ProjectionWorkerRuntime(
        _ProjectionWorker(projection_service, worker_id=worker_id or f"projection-{socket.gethostname()}")
    )


def main() -> None:
    runtime = create_projection_worker_runtime()
    signal.signal(signal.SIGINT, runtime.stop)
    signal.signal(signal.SIGTERM, runtime.stop)
    runtime.run_forever()


# -- Internal worker implementation -------------------------------------------


class _ProjectionWorker:
    """Background worker that reconciles pending projections."""

    def __init__(self, service: OntologyProjectionService, worker_id: str) -> None:
        self._service = service
        self._worker_id = worker_id
        self._poll_seconds = 30
        self._batch_size = 50

    def run_forever(self, stop_event: Event) -> None:
        """Poll for pending projections and reconcile."""
        import time

        while not stop_event.is_set():
            try:
                self._reconcile_cycle()
            except Exception:  # noqa: BLE001 - worker retries on its next polling cycle.
                # Never crash the worker; retry next cycle.
                time.sleep(self._poll_seconds)
            stop_event.wait(self._poll_seconds)

    def _reconcile_cycle(self) -> None:
        """One reconciliation cycle: find pending, reconcile, repeat."""
        # We need to discover organizations. Use a default or scan Neo4j.
        # For now, reconcile all pending across the graph (tenant-scoped queries).
        self._service.reconcile_all_pending(
            organization_id="*",  # Wildcard: reconciles all orgs in Neo4j
            limit=self._batch_size,
        )


if __name__ == "__main__":
    main()
