from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Lock

from ai_governance.domain.jobs import (
    IdempotencyConflictError,
    Job,
    JobStatus,
    JobType,
    WorkerHeartbeat,
)
from ai_governance.repositories.job_repository import JobRepository


class InMemoryJobRepository(JobRepository):
    """
    In-memory JobRepository used by tests and local workflows.
    """

    def __init__(self) -> None:
        self._jobs_by_id: dict[str, Job] = {}
        self._workers: dict[str, WorkerHeartbeat] = {}
        self._claim_lock = Lock()

    def register_worker(self, worker: WorkerHeartbeat) -> None:
        self._workers[worker.worker_id] = worker

    def heartbeat_worker(self, worker_id: str, heartbeat_at) -> None:
        current = self._workers.get(worker_id)
        if current is not None:
            self._workers[worker_id] = replace(current, heartbeat_at=heartbeat_at)

    def list_worker_heartbeats(self) -> list[WorkerHeartbeat]:
        return list(self._workers.values())

    def save(
        self,
        job: Job,
    ) -> None:
        existing = self.find_by_idempotency_key(
            job.job_type.value,
            job.idempotency_key,
            job.execution_context.organization_id if job.execution_context else None,
            job.execution_context.project_id if job.execution_context else None,
        )
        if existing is not None and (
            existing.job_id != job.job_id or existing.input_hash != job.input_hash
        ):
            raise IdempotencyConflictError(
                "Idempotency key was reused with different input."
            )
        self._jobs_by_id[job.job_id] = job

    def find_by_id(
        self,
        job_id: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> Job | None:
        job = self._jobs_by_id.get(job_id)
        if job is None:
            return None
        context = job.execution_context
        if organization_id is not None and (
            context is None or context.organization_id != organization_id
        ):
            return None
        if project_id is not None and (
            context is None or context.project_id != project_id
        ):
            return None
        return job

    def find_by_idempotency_key(
        self,
        job_type: str,
        idempotency_key: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> Job | None:
        return next(
            (
                job
                for job in self._jobs_by_id.values()
                if job.job_type.value == job_type
                and job.idempotency_key == idempotency_key
                and (
                    organization_id is None
                    or (
                        job.execution_context
                        and job.execution_context.organization_id == organization_id
                    )
                )
                and (
                    project_id is None
                    or (
                        job.execution_context
                        and job.execution_context.project_id == project_id
                    )
                )
            ),
            None,
        )

    def list_by_status(
        self,
        status: JobStatus,
        limit: int = 100,
    ) -> list[Job]:
        return self.list_jobs(status=status, limit=limit)

    def list_jobs(
        self,
        status: JobStatus | None = None,
        job_type: JobType | None = None,
        limit: int = 100,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> list[Job]:
        return [
            job
            for job in sorted(
                self._jobs_by_id.values(),
                key=lambda item: (item.created_at, item.job_id),
            )
            if (status is None or job.status == status)
            and (job_type is None or job.job_type == job_type)
            and (
                organization_id is None
                or (
                    job.execution_context
                    and job.execution_context.organization_id == organization_id
                )
                or (job.execution_context is None and organization_id == "org_default")
            )
            and (
                project_id is None
                or (
                    job.execution_context
                    and job.execution_context.project_id == project_id
                )
                or (job.execution_context is None and project_id == "project_default")
            )
        ][:limit]

    def acquire_next_queued_job(
        self,
        worker_id: str,
        lease_seconds: int,
        job_types: tuple[JobType, ...] | None = None,
        job_operations: Mapping[JobType, tuple[str, ...]] | None = None,
    ) -> Job | None:
        with self._claim_lock:
            queued_jobs = self.list_by_status(JobStatus.QUEUED)
            if job_types:
                queued_jobs = [job for job in queued_jobs if job.job_type in job_types]
            if job_operations:
                queued_jobs = [
                    job
                    for job in queued_jobs
                    if job.job_type not in job_operations
                    or str(job.input_refs.get("operation", ""))
                    in job_operations[job.job_type]
                ]
            queued_jobs = queued_jobs[:1]
            if not queued_jobs:
                return None
            now = datetime.now(UTC)
            job = queued_jobs[0]
            acquired = replace(
                job,
                status=JobStatus.RUNNING,
                attempt_count=job.attempt_count + 1,
                leased_by=worker_id,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                heartbeat_at=now,
                started_at=job.started_at or now,
                updated_at=now,
            )
            self.save(acquired)
            return acquired

    def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        job = self.find_by_id(job_id)
        if job is None or job.status != JobStatus.RUNNING or job.leased_by != worker_id:
            return

        now = datetime.now(UTC)
        self.save(
            replace(
                job,
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
        )

    def mark_succeeded(
        self,
        job_id: str,
        result_ref: str,
    ) -> None:
        job = self.find_by_id(job_id)
        if job is None or job.status is JobStatus.CANCELLED:
            return

        now = datetime.now(UTC)
        self.save(
            replace(
                job,
                status=JobStatus.SUCCEEDED,
                result_ref=result_ref,
                failure_reason=None,
                leased_by=None,
                lease_expires_at=None,
                heartbeat_at=None,
                updated_at=now,
                completed_at=now,
            )
        )

    def mark_failed(
        self,
        job_id: str,
        failure_reason: str,
    ) -> None:
        job = self.find_by_id(job_id)
        if job is None or job.status is JobStatus.CANCELLED:
            return

        now = datetime.now(UTC)
        self.save(
            replace(
                job,
                status=JobStatus.FAILED,
                result_ref=None,
                failure_reason=failure_reason,
                leased_by=None,
                lease_expires_at=None,
                heartbeat_at=None,
                updated_at=now,
                completed_at=now,
            )
        )

    def cancel(
        self,
        job_id: str,
    ) -> None:
        job = self.find_by_id(job_id)
        if job is None:
            return

        now = datetime.now(UTC)
        self.save(
            replace(
                job,
                status=JobStatus.CANCELLED,
                leased_by=None,
                lease_expires_at=None,
                heartbeat_at=None,
                updated_at=now,
                completed_at=now,
            )
        )

    def release_expired_leases(self) -> int:
        now = datetime.now(UTC)
        released = 0
        for job in list(self._jobs_by_id.values()):
            if (
                job.status != JobStatus.RUNNING
                or job.lease_expires_at is None
                or job.lease_expires_at > now
            ):
                continue

            if job.attempt_count < job.max_attempts:
                self.save(
                    replace(
                        job,
                        status=JobStatus.QUEUED,
                        leased_by=None,
                        lease_expires_at=None,
                        heartbeat_at=None,
                        updated_at=now,
                    )
                )
            else:
                self.save(
                    replace(
                        job,
                        status=JobStatus.FAILED,
                        failure_reason="Job lease expired after max attempts.",
                        leased_by=None,
                        lease_expires_at=None,
                        heartbeat_at=None,
                        updated_at=now,
                        completed_at=now,
                    )
                )
            released += 1

        return released
