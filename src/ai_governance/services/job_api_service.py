from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import final
from uuid import uuid4

from ai_governance.domain.jobs import Job, JobStatus, JobSubmission, JobType
from ai_governance.events import EventPublisher, ResourceLifecycleEvent
from ai_governance.ontology.synchronization import (
    OntologySyncEventPublisherProtocol,
)
from ai_governance.repositories.job_repository import JobRepository
from ai_governance.services.job_submission_service import JobSubmissionService
from ai_governance.settings_control.operational import duration_seconds, setting_context
from ai_governance.tenancy.domain import TenantContext


class JobNotFoundError(Exception):
    """
    Raised when a job cannot be found by ID.
    """

    def __init__(
        self,
        job_id: str,
    ) -> None:
        super().__init__(f"Job '{job_id}' was not found.")
        self.job_id = job_id


class InvalidJobRequestError(ValueError):
    """
    Raised when a public job operation is invalid for the current job state.
    """


@final
class JobApiService:
    """
    REST-facing facade for public job control-plane operations.
    """

    def __init__(
        self,
        repository: JobRepository,
        submission_service: JobSubmissionService | None = None,
        retry_id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol | None = None,
        configuration_service=None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self._repository = repository
        self._ontology_event_publisher = ontology_event_publisher
        self._submission_service = submission_service or JobSubmissionService(
            repository,
            ontology_event_publisher=ontology_event_publisher,
            configuration_service=configuration_service,
            event_publisher=event_publisher,
        )
        self._configuration_service = configuration_service
        self._retry_id_generator = retry_id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._event_publisher = event_publisher

    def submit(
        self,
        submission: JobSubmission,
    ) -> Job:
        """
        Submit a new job or return an existing idempotent job.
        """
        return self._submission_service.submit(submission)

    def get(
        self,
        job_id: str,
        context: TenantContext | None = None,
    ) -> Job:
        """
        Return a job by ID or raise if it does not exist.
        """
        job = self._repository.find_by_id(
            job_id,
            context.organization_id if context else None,
            context.project_id if context else None,
        )
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def list_jobs(
        self,
        status: JobStatus | None = None,
        job_type: JobType | None = None,
        limit: int = 100,
        context: TenantContext | None = None,
    ) -> list[Job]:
        """
        List jobs using optional status and type filters.
        """
        if not 1 <= limit <= 500:
            raise InvalidJobRequestError("limit must be between 1 and 500.")
        jobs = self._repository.list_jobs(
            status=status,
            job_type=job_type,
            limit=limit,
            organization_id=context.organization_id if context else None,
            project_id=context.project_id if context else None,
        )
        if self._configuration_service is None:
            return jobs
        retention = duration_seconds(
            self._configuration_service.get("jobs.retention", setting_context(context))
        )
        cutoff = self._clock().timestamp() - retention
        return [
            job
            for job in jobs
            if job.status
            not in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
            or (job.completed_at or job.updated_at).timestamp() >= cutoff
        ]

    def cancel(
        self,
        job_id: str,
        context: TenantContext | None = None,
    ) -> Job:
        """
        Cancel a queued job, or best-effort cancel a running job.
        """
        job = self.get(job_id, context)
        if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
            raise InvalidJobRequestError(
                f"Job '{job_id}' cannot be cancelled from {job.status.value} status."
            )

        job = self._repository.find_by_id(job_id)
        self._repository.cancel(job_id)
        if job is not None:
            self._publish_lifecycle_event(job, "cancelled")
        cancelled = self.get(job_id, context)
        self._publish_job_event("JobCancelled", cancelled)
        return cancelled

    def retry(
        self,
        job_id: str,
        context: TenantContext | None = None,
    ) -> Job:
        """
        Requeue a failed job or create a new queued retry job.
        """
        job = self.get(job_id, context)
        if job.status != JobStatus.FAILED:
            raise InvalidJobRequestError(
                f"Job '{job_id}' can only be retried from FAILED status."
            )

        if self._configuration_service is not None:
            retry_delay = duration_seconds(
                self._configuration_service.get(
                    "jobs.retry_delay", setting_context(context)
                )
            )
            retry_at = (job.completed_at or job.updated_at).timestamp() + retry_delay
            if self._clock().timestamp() < retry_at:
                raise InvalidJobRequestError(
                    f"Job '{job_id}' cannot be retried until its configured retry delay has elapsed."
                )

        if job.attempt_count < job.max_attempts:
            now = self._clock()
            retried = replace(
                job,
                status=JobStatus.QUEUED,
                result_ref=None,
                failure_reason=None,
                leased_by=None,
                lease_expires_at=None,
                heartbeat_at=None,
                updated_at=now,
                completed_at=None,
            )
            self._repository.save(retried)
            self._publish_job_event("JobRetried", retried)
            self._publish_lifecycle_event(retried, "queued")
            return retried

        return self._submission_service.submit(
            JobSubmission(
                job_type=job.job_type,
                input_refs=job.input_refs,
                idempotency_key=(
                    f"{job.idempotency_key}:retry:{self._retry_id_generator()}"
                ),
                submitted_by=job.submitted_by,
                max_attempts=job.max_attempts,
                execution_context=job.execution_context,
            )
        )

    def get_result(
        self,
        job_id: str,
        context: TenantContext | None = None,
    ) -> Job:
        """
        Return the job state used by the result endpoint.
        """
        return self.get(job_id, context)

    def _publish_job_event(
        self,
        event_type: str,
        job: Job,
    ) -> None:
        if self._ontology_event_publisher is None:
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
            organization_id=(
                job.execution_context.organization_id
                if job.execution_context
                else "org_default"
            ),
            project_id=(
                job.execution_context.project_id
                if job.execution_context
                else "project_default"
            ),
        )

    def _publish_lifecycle_event(self, job: Job, state: str) -> None:
        """Publish a generic job transition after the repository transition."""
        if self._event_publisher is None or job.execution_context is None:
            return
        execution_context = job.execution_context
        asyncio.run(
            self._event_publisher.publish(
                ResourceLifecycleEvent(
                    tenant={
                        "organization_id": execution_context.organization_id,
                        "project_id": execution_context.project_id or "",
                    },
                    resource_kind="job",
                    resource_id=job.job_id,
                    state=state,
                    payload={"job_type": job.job_type.value},
                )
            )
        )
