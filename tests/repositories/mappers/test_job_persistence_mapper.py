from __future__ import annotations

from datetime import UTC, datetime

from ai_governance.domain.jobs import Job, JobStatus, JobType
from ai_governance.repositories.mappers.job_persistence_mapper import (
    JobPersistenceMapper,
)


def test_job_mapper_round_trips_job() -> None:
    job = Job(
        job_id="job-1",
        job_type=JobType.EXPERIMENT,
        status=JobStatus.RUNNING,
        input_refs={"b": 2, "a": 1},
        input_hash="hash-1",
        idempotency_key="key-1",
        submitted_by="tester",
        attempt_count=1,
        max_attempts=3,
        result_ref=None,
        failure_reason=None,
        leased_by="worker-1",
        lease_expires_at=datetime(2026, 6, 28, 0, 5, tzinfo=UTC),
        heartbeat_at=datetime(2026, 6, 28, 0, 1, tzinfo=UTC),
        created_at=datetime(2026, 6, 28, tzinfo=UTC),
        updated_at=datetime(2026, 6, 28, 0, 1, tzinfo=UTC),
        started_at=datetime(2026, 6, 28, tzinfo=UTC),
        completed_at=None,
    )

    record = JobPersistenceMapper.to_persistence_record(job)

    assert record["input_refs_json"] == '{"a":1,"b":2}'
    assert JobPersistenceMapper.from_persistence_record(record) == job
