from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from kavach.domain.jobs import Job, JobStatus, JobType, WorkerHeartbeat


class JobRepository(ABC):
    """
    Persistence contract for governance jobs.
    """

    def register_worker(self, worker: WorkerHeartbeat) -> None:
        """Record worker liveness; optional for legacy repository adapters."""

    def heartbeat_worker(self, worker_id: str, heartbeat_at) -> None:
        """Update a worker liveness timestamp."""

    def list_worker_heartbeats(self) -> list[WorkerHeartbeat]:
        """Return the latest heartbeat for each known worker."""
        return []

    @abstractmethod
    def save(
        self,
        job: Job,
    ) -> None:
        pass

    @abstractmethod
    def find_by_id(
        self,
        job_id: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> Job | None:
        pass

    @abstractmethod
    def find_by_idempotency_key(
        self,
        job_type: str,
        idempotency_key: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> Job | None:
        pass

    @abstractmethod
    def list_by_status(
        self,
        status: JobStatus,
        limit: int = 100,
    ) -> list[Job]:
        pass

    @abstractmethod
    def list_jobs(
        self,
        status: JobStatus | None = None,
        job_type: JobType | None = None,
        limit: int = 100,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> list[Job]:
        pass

    @abstractmethod
    def acquire_next_queued_job(
        self,
        worker_id: str,
        lease_seconds: int,
        job_types: tuple[JobType, ...] | None = None,
        job_operations: Mapping[JobType, tuple[str, ...]] | None = None,
    ) -> Job | None:
        pass

    @abstractmethod
    def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        pass

    @abstractmethod
    def mark_succeeded(
        self,
        job_id: str,
        result_ref: str,
    ) -> None:
        pass

    @abstractmethod
    def mark_failed(
        self,
        job_id: str,
        failure_reason: str,
    ) -> None:
        pass

    @abstractmethod
    def cancel(
        self,
        job_id: str,
    ) -> None:
        pass

    @abstractmethod
    def release_expired_leases(self) -> int:
        pass
