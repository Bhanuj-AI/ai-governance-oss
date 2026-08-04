from __future__ import annotations

from datetime import UTC, datetime

from kavach.domain.jobs import WorkerHeartbeat
from kavach.services.dashboard_service import _worker_health


def test_worker_health_excludes_demo_heartbeats_from_the_live_count() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)

    status, detail = _worker_health(
        [
            WorkerHeartbeat("worker-local-1", "demo", now),
            WorkerHeartbeat("worker-local-2", "demo", now),
            WorkerHeartbeat("replay-worker-local", "job", now),
        ],
        now=now,
    )

    assert status == "Healthy"
    assert detail.startswith("1 active worker")


def test_worker_health_is_unknown_when_only_demo_workers_exist() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)

    status, detail = _worker_health(
        [WorkerHeartbeat("worker-local-1", "demo", now)], now=now
    )

    assert status == "Unknown"
    assert detail == "No active job workers have registered a heartbeat."
