from __future__ import annotations

from datetime import UTC, datetime
from collections.abc import Mapping
import asyncio

from kavach.domain.jobs import Job, JobStatus, JobType, WorkerHeartbeat
from kavach.ontology.synchronization import (
    OntologySyncEventPublisherProtocol,
)
from kavach.repositories.job_repository import JobRepository
from kavach.services.job_executor import JobExecutor
from kavach.events import EventPublisher, ResourceLifecycleEvent


class JobWorker:
    """
    Executes queued governance jobs using repository leases.
    """

    def __init__(
        self,
        worker_id: str,
        repository: JobRepository,
        executor: JobExecutor,
        lease_seconds: int = 300,
        job_types: tuple[JobType, ...] | None = None,
        job_operations: Mapping[JobType, tuple[str, ...]] | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol | None = None,
        configuration_service=None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self._worker_id = worker_id
        self._repository = repository
        self._executor = executor
        self._lease_seconds = lease_seconds
        self._job_types = job_types
        self._job_operations = dict(job_operations or {})
        self._ontology_event_publisher = ontology_event_publisher
        self._configuration_service = configuration_service
        self._event_publisher = event_publisher
        self._repository.register_worker(
            WorkerHeartbeat(
                worker_id=worker_id,
                worker_type="job",
                heartbeat_at=datetime.now(UTC),
            )
        )

    def run_once(self) -> Job | None:
        """
        Release expired leases, acquire one queued job, and execute it.
        """
        self._repository.heartbeat_worker(self._worker_id, datetime.now(UTC))
        self._repository.release_expired_leases()
        if self._configuration_service is not None:
            concurrency = int(
                self._configuration_service.get("jobs.worker_concurrency")
            )
            if (
                len(
                    self._repository.list_jobs(
                        status=JobStatus.RUNNING,
                        limit=concurrency,
                    )
                )
                >= concurrency
            ):
                return None
        job = self._repository.acquire_next_queued_job(
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
            job_types=self._job_types,
            job_operations=self._job_operations,
        )
        if job is None:
            return None

        self._publish_lifecycle_event(job, "started")

        try:
            result = self._executor.execute(job)
            if result.status == JobStatus.SUCCEEDED and result.result_ref:
                self._repository.mark_succeeded(
                    job.job_id,
                    result.result_ref,
                )
                self._publish_job_event("JobCompleted", job.job_id)
                self._publish_lifecycle_event(job, "completed")
            elif result.status == JobStatus.CANCELLED:
                self._repository.cancel(job.job_id)
                self._publish_job_event("JobCancelled", job.job_id)
                self._publish_lifecycle_event(job, "cancelled")
            else:
                self._repository.mark_failed(
                    job.job_id,
                    result.failure_reason or "Job execution failed.",
                )
                self._publish_job_event("JobFailed", job.job_id)
                self._publish_lifecycle_event(job, "failed")
        except Exception as exc:
            self._repository.mark_failed(job.job_id, str(exc))
            self._publish_job_event("JobFailed", job.job_id)
            self._publish_lifecycle_event(job, "failed")
            raise

        return self._repository.find_by_id(job.job_id)

    def _publish_lifecycle_event(self, job: Job, state: str) -> None:
        """Publish an optional generic lifecycle fact after durable job transition."""
        if self._event_publisher is None or job.execution_context is None:
            return
        asyncio.run(self._event_publisher.publish(ResourceLifecycleEvent(tenant={"organization_id": job.execution_context.organization_id, "project_id": job.execution_context.project_id or ""}, resource_kind="job", resource_id=job.job_id, state=state, payload={"job_type": job.job_type.value})))

    def _publish_job_event(
        self,
        event_type: str,
        job_id: str,
    ) -> None:
        if self._ontology_event_publisher is None:
            return
        job = self._repository.find_by_id(job_id)
        if job is None:
            return
        self._ontology_event_publisher.publish_entity_event(
            event_type,
            entity_type="Job",
            entity_id=job.job_id,
            scope_identifier="job_control_plane",
            payload={
                "job_id": job.job_id,
                "job_type": job.job_type.value,
                "status": job.status.value,
            },
        )
