from __future__ import annotations

from ai_governance.domain.jobs import Job, JobResult, JobStatus, JobSubmission, JobType
from ai_governance.repositories.in_memory import InMemoryJobRepository
from ai_governance.services.job_executor import JobExecutor
from ai_governance.services.job_submission_service import JobSubmissionService
from ai_governance.workers import JobWorker


class SuccessfulEvaluationHandler:
    def handle(
        self,
        job: Job,
    ) -> JobResult:
        return JobResult(
            job_id=job.job_id,
            status=JobStatus.SUCCEEDED,
            result_ref=f"evaluation:{job.input_refs['execution_id']}",
            failure_reason=None,
        )


class FailedDriftHandler:
    def handle(
        self,
        job: Job,
    ) -> JobResult:
        return JobResult(
            job_id=job.job_id,
            status=JobStatus.FAILED,
            result_ref=None,
            failure_reason="Synthetic drift handler failure.",
        )


def main() -> None:
    repository = InMemoryJobRepository()
    submission_service = JobSubmissionService(
        repository,
        id_generator=_id_generator(),
    )

    evaluation_job = submission_service.submit(
        JobSubmission(
            job_type=JobType.EVALUATION,
            input_refs={"execution_id": "worker-execution-1"},
            idempotency_key="worker-evaluation-1",
            submitted_by="smoke-test",
        )
    )
    drift_job = submission_service.submit(
        JobSubmission(
            job_type=JobType.DRIFT_ANALYSIS,
            input_refs={
                "baseline_evaluation_id": "eval-1",
                "candidate_evaluation_id": "eval-2",
            },
            idempotency_key="worker-drift-1",
            submitted_by="smoke-test",
        )
    )

    worker = JobWorker(
        worker_id="worker-smoke-1",
        repository=repository,
        executor=JobExecutor(
            {
                JobType.EVALUATION: SuccessfulEvaluationHandler(),
                JobType.DRIFT_ANALYSIS: FailedDriftHandler(),
            }
        ),
        lease_seconds=60,
    )

    first = worker.run_once()
    second = worker.run_once()
    third = worker.run_once()

    print("[submitted]")
    print(f"evaluation_job={evaluation_job.job_id}:{evaluation_job.status.value}")
    print(f"drift_job={drift_job.job_id}:{drift_job.status.value}")
    print()
    print("[worker runs]")
    print(f"first={_summary(first)}")
    print(f"second={_summary(second)}")
    print(f"third={third}")
    print()
    print("[final repository state]")
    for job in repository.list_jobs():
        print(
            f"{job.job_id} type={job.job_type.value} "
            f"status={job.status.value} attempts={job.attempt_count} "
            f"result_ref={job.result_ref} failure={job.failure_reason}"
        )


def _id_generator():
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"job-smoke-{counter}"

    return next_id


def _summary(
    job: Job | None,
) -> str | None:
    if job is None:
        return None
    return (
        f"{job.job_id}:{job.job_type.value}:{job.status.value}:"
        f"attempts={job.attempt_count}"
    )


if __name__ == "__main__":
    main()
