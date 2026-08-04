from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Thread

import pytest

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.domain.jobs import (
    IdempotencyConflictError,
    Job,
    JobStatus,
    JobType,
)
from kavach.repositories.sqlite.sqlite_job_repository import SQLiteJobRepository


@pytest.fixture
def repository(
    tmp_path: Path,
) -> SQLiteJobRepository:
    database = SQLiteDatabase(tmp_path / "kavach.db")
    database.initialize()
    return SQLiteJobRepository(database)


def test_saves_and_retrieves_job(
    repository: SQLiteJobRepository,
) -> None:
    job = _job()

    repository.save(job)

    assert repository.find_by_id(job.job_id) == job


def test_preserves_input_refs_and_datetime_fields(
    repository: SQLiteJobRepository,
) -> None:
    job = _job(input_refs={"nested": {"b": 2, "a": 1}})

    repository.save(job)
    loaded = repository.find_by_id(job.job_id)

    assert loaded is not None
    assert loaded.input_refs == {"nested": {"b": 2, "a": 1}}
    assert loaded.created_at == job.created_at


def test_enforces_idempotency_lookup(
    repository: SQLiteJobRepository,
) -> None:
    job = _job()
    repository.save(job)

    assert repository.find_by_idempotency_key(
        JobType.EVALUATION.value,
        "key-1",
    ) == job

    with pytest.raises(IdempotencyConflictError):
        repository.save(
            _job(
                job_id="job-2",
                idempotency_key="key-1",
                input_hash="different",
            )
        )


def test_lists_jobs_with_optional_filters(
    repository: SQLiteJobRepository,
) -> None:
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


def test_acquires_queued_job(
    repository: SQLiteJobRepository,
) -> None:
    repository.save(_job())

    acquired = repository.acquire_next_queued_job("worker-1", 300)

    assert acquired is not None
    assert acquired.status == JobStatus.RUNNING
    assert acquired.attempt_count == 1


def test_acquire_can_require_an_async_job_operation(
    repository: SQLiteJobRepository,
) -> None:
    repository.save(_job())
    valid = _job(
        job_id="job-2",
        idempotency_key="key-2",
        input_refs={
            "operation": "evaluation.submit_async",
            "execution_id": "exec-2",
            "metadata": {"source": "worker-test"},
        },
    )
    repository.save(valid)

    acquired = repository.acquire_next_queued_job(
        "worker-1",
        300,
        job_types=(JobType.EVALUATION,),
        job_operations={JobType.EVALUATION: ("evaluation.submit_async",)},
    )

    assert acquired is not None
    assert acquired.job_id == "job-2"
    assert repository.find_by_id("job-1").status is JobStatus.QUEUED


def test_competing_workers_claim_a_queued_job_exactly_once(
    repository: SQLiteJobRepository,
) -> None:
    repository.save(_job())
    barrier = Barrier(2)
    claims = []

    def claim(worker_id: str) -> None:
        barrier.wait()
        claims.append(repository.acquire_next_queued_job(worker_id, 300))

    first = Thread(target=claim, args=("worker-1",))
    second = Thread(target=claim, args=("worker-2",))
    first.start()
    second.start()
    first.join()
    second.join()

    claimed = [job for job in claims if job is not None]
    assert len(claimed) == 1
    assert claimed[0].attempt_count == 1


def test_marks_succeeded_with_result_ref(
    repository: SQLiteJobRepository,
) -> None:
    repository.save(_job())

    repository.mark_succeeded("job-1", "evaluation:eval-1")

    job = repository.find_by_id("job-1")
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED
    assert job.result_ref == "evaluation:eval-1"


def test_marks_failed_with_failure_reason(
    repository: SQLiteJobRepository,
) -> None:
    repository.save(_job())

    repository.mark_failed("job-1", "failed")

    job = repository.find_by_id("job-1")
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert job.failure_reason == "failed"


def test_releases_expired_leases(
    repository: SQLiteJobRepository,
) -> None:
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


def _job(
    job_id: str = "job-1",
    idempotency_key: str = "key-1",
    input_hash: str = "hash-1",
    input_refs: dict[str, object] | None = None,
) -> Job:
    now = datetime(2026, 6, 28, tzinfo=UTC)
    return Job(
        job_id=job_id,
        job_type=JobType.EVALUATION,
        status=JobStatus.QUEUED,
        input_refs=input_refs or {"execution_id": "exec-1"},
        input_hash=input_hash,
        idempotency_key=idempotency_key,
        submitted_by="tester",
        attempt_count=0,
        max_attempts=3,
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
