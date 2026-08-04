from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from kavach.domain.jobs import Job, JobStatus, JobType
from kavach.repositories.in_memory import InMemoryJobRepository


def test_saves_and_retrieves_job() -> None:
    repository = InMemoryJobRepository()
    job = _job()

    repository.save(job)

    assert repository.find_by_id(job.job_id) == job


def test_lists_jobs_by_status() -> None:
    repository = InMemoryJobRepository()
    queued = _job(job_id="job-1")
    failed = replace(_job(job_id="job-2", idempotency_key="key-2"), status=JobStatus.FAILED)

    repository.save(queued)
    repository.save(failed)

    assert repository.list_by_status(JobStatus.QUEUED) == [queued]


def test_lists_jobs_with_optional_filters() -> None:
    repository = InMemoryJobRepository()
    evaluation = _job(job_id="job-1", idempotency_key="key-1")
    drift = replace(
        _job(job_id="job-2", idempotency_key="key-2"),
        job_type=JobType.DRIFT_ANALYSIS,
        status=JobStatus.FAILED,
    )
    repository.save(evaluation)
    repository.save(drift)

    assert repository.list_jobs(
        status=JobStatus.FAILED,
        job_type=JobType.DRIFT_ANALYSIS,
    ) == [drift]


def test_acquires_oldest_queued_job() -> None:
    repository = InMemoryJobRepository()
    newer = _job(job_id="job-2", idempotency_key="key-2")
    older = _job(
        job_id="job-1",
        idempotency_key="key-1",
        created_at=datetime(2026, 6, 27, tzinfo=UTC),
    )
    repository.save(newer)
    repository.save(older)

    acquired = repository.acquire_next_queued_job("worker-1", 300)

    assert acquired is not None
    assert acquired.job_id == "job-1"


def test_acquired_job_becomes_running_and_attempt_count_increments() -> None:
    repository = InMemoryJobRepository()
    repository.save(_job())

    acquired = repository.acquire_next_queued_job("worker-1", 300)

    assert acquired is not None
    assert acquired.status == JobStatus.RUNNING
    assert acquired.leased_by == "worker-1"
    assert acquired.lease_expires_at is not None
    assert acquired.started_at is not None
    assert acquired.attempt_count == 1


def test_expired_lease_returns_job_to_queued() -> None:
    repository = InMemoryJobRepository()
    running = replace(
        _job(),
        status=JobStatus.RUNNING,
        attempt_count=1,
        leased_by="worker-1",
        lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    repository.save(running)

    released = repository.release_expired_leases()

    assert released == 1
    job = repository.find_by_id(running.job_id)
    assert job is not None
    assert job.status == JobStatus.QUEUED
    assert job.leased_by is None


def test_expired_lease_with_max_attempts_marks_failed() -> None:
    repository = InMemoryJobRepository()
    running = replace(
        _job(max_attempts=1),
        status=JobStatus.RUNNING,
        attempt_count=1,
        leased_by="worker-1",
        lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    repository.save(running)

    repository.release_expired_leases()

    job = repository.find_by_id(running.job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert job.failure_reason == "Job lease expired after max attempts."


def test_cancelled_job_cannot_be_acquired() -> None:
    repository = InMemoryJobRepository()
    job = _job()
    repository.save(job)
    repository.cancel(job.job_id)

    assert repository.acquire_next_queued_job("worker-1", 300) is None


def _job(
    job_id: str = "job-1",
    idempotency_key: str = "key-1",
    created_at: datetime | None = None,
    max_attempts: int = 3,
) -> Job:
    now = created_at or datetime(2026, 6, 28, tzinfo=UTC)
    return Job(
        job_id=job_id,
        job_type=JobType.EVALUATION,
        status=JobStatus.QUEUED,
        input_refs={"execution_id": "exec-1"},
        input_hash=f"hash-{job_id}",
        idempotency_key=idempotency_key,
        submitted_by="tester",
        attempt_count=0,
        max_attempts=max_attempts,
        result_ref=None,
        failure_reason=None,
        leased_by=None,
        lease_expires_at=None,
        heartbeat_at=None,
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
