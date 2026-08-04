from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from kavach.domain.jobs import Job, JobResult, JobStatus, JobType
from kavach.plugins.contracts import JobHandlerDefinition
from kavach.repositories.in_memory import InMemoryJobRepository
from kavach.services.job_executor import JobExecutor, register_extension_handlers
from kavach.workers import JobWorker


class SuccessfulHandler:
    def handle(
        self,
        job: Job,
    ) -> JobResult:
        return JobResult(
            job_id=job.job_id,
            status=JobStatus.SUCCEEDED,
            result_ref="evaluation:eval-1",
            failure_reason=None,
        )


class FailingHandler:
    def handle(
        self,
        job: Job,
    ) -> JobResult:
        raise RuntimeError("boom")


def test_executor_dispatches_a_namespaced_extension_operation() -> None:
    register_extension_handlers(
        [
            JobHandlerDefinition(
                job_type=JobType.EXTENSION,
                operation="tests.slo-evaluation",
                handler=SuccessfulHandler(),
            )
        ]
    )
    job = replace(
        _job(),
        job_type=JobType.EXTENSION,
        input_refs={"_kavach_extension": {"operation": "tests.slo-evaluation"}},
    )

    result = JobExecutor().execute(job)

    assert result.status is JobStatus.SUCCEEDED


def test_worker_returns_none_when_no_queued_jobs_exist() -> None:
    repository = InMemoryJobRepository()
    worker = JobWorker(
        worker_id="worker-1",
        repository=repository,
        executor=JobExecutor(),
    )

    assert worker.run_once() is None


def test_worker_executes_queued_job_successfully() -> None:
    repository = InMemoryJobRepository()
    repository.save(_job())
    worker = JobWorker(
        worker_id="worker-1",
        repository=repository,
        executor=JobExecutor({JobType.EVALUATION: SuccessfulHandler()}),
    )

    result = worker.run_once()

    assert result is not None
    assert result.status == JobStatus.SUCCEEDED


def test_worker_persists_result_ref_on_success() -> None:
    repository = InMemoryJobRepository()
    repository.save(_job())
    worker = JobWorker(
        worker_id="worker-1",
        repository=repository,
        executor=JobExecutor({JobType.EVALUATION: SuccessfulHandler()}),
    )

    worker.run_once()

    job = repository.find_by_id("job-1")
    assert job is not None
    assert job.result_ref == "evaluation:eval-1"


def test_worker_persists_failure_reason_on_handler_exception() -> None:
    repository = InMemoryJobRepository()
    repository.save(_job())
    worker = JobWorker(
        worker_id="worker-1",
        repository=repository,
        executor=JobExecutor({JobType.EVALUATION: FailingHandler()}),
    )

    with pytest.raises(RuntimeError):
        worker.run_once()

    job = repository.find_by_id("job-1")
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert job.failure_reason == "boom"


def test_worker_does_not_execute_cancelled_jobs() -> None:
    repository = InMemoryJobRepository()
    repository.save(_job())
    repository.cancel("job-1")
    worker = JobWorker(
        worker_id="worker-1",
        repository=repository,
        executor=JobExecutor({JobType.EVALUATION: SuccessfulHandler()}),
    )

    assert worker.run_once() is None


def test_worker_only_claims_configured_job_types() -> None:
    repository = InMemoryJobRepository()
    repository.save(_job())
    worker = JobWorker(
        worker_id="worker-1",
        repository=repository,
        executor=JobExecutor({JobType.EVALUATION: SuccessfulHandler()}),
        job_types=(JobType.EXPERIMENT,),
    )

    assert worker.run_once() is None
    assert repository.find_by_id("job-1").status is JobStatus.QUEUED


def test_worker_only_claims_configured_job_operations() -> None:
    repository = InMemoryJobRepository()
    repository.save(_job())
    worker = JobWorker(
        worker_id="worker-1",
        repository=repository,
        executor=JobExecutor({JobType.EVALUATION: SuccessfulHandler()}),
        job_types=(JobType.EVALUATION,),
        job_operations={JobType.EVALUATION: ("evaluation.submit_async",)},
    )

    assert worker.run_once() is None
    assert repository.find_by_id("job-1").status is JobStatus.QUEUED


def _job() -> Job:
    now = datetime(2026, 6, 28, tzinfo=UTC)
    return Job(
        job_id="job-1",
        job_type=JobType.EVALUATION,
        status=JobStatus.QUEUED,
        input_refs={"execution_id": "exec-1"},
        input_hash="hash-1",
        idempotency_key="key-1",
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
