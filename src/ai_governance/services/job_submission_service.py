from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ai_governance.domain.jobs import (
    IdempotencyConflictError,
    Job,
    JobStatus,
    JobSubmission,
)
from ai_governance.events import EventPublisher, ResourceLifecycleEvent
from ai_governance.ontology.synchronization import (
    OntologySyncEventPublisherProtocol,
)
from ai_governance.repositories.job_repository import JobRepository
from ai_governance.repositories.mappers.job_persistence_mapper import (
    JobPersistenceMapper,
)
from ai_governance.settings_control.operational import setting_context


class JobSubmissionValidationError(ValueError):
    """
    Raised when a job submission fails validation.
    """


class JobSubmissionService:
    """
    Submits governance jobs with stable idempotency semantics.
    """

    def __init__(
        self,
        repository: JobRepository,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol | None = None,
        configuration_service: Any | None = None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self.repository = repository
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ontology_event_publisher = ontology_event_publisher
        self._configuration_service = configuration_service
        self._event_publisher = event_publisher

    def submit(
        self,
        submission: JobSubmission,
    ) -> Job:
        """
        Submit a job or return the existing idempotent job.
        """
        self._validate(submission)
        context = submission.execution_context
        input_hash = stable_input_hash(
            submission.input_refs,
            organization_id=context.organization_id if context else None,
            project_id=context.project_id if context else None,
        )
        existing = self.repository.find_by_idempotency_key(
            submission.job_type.value,
            submission.idempotency_key,
            context.organization_id if context else None,
            context.project_id if context else None,
        )
        if existing is not None:
            if existing.input_hash != input_hash:
                raise IdempotencyConflictError(
                    "Idempotency key was reused with different input."
                )
            return existing

        if self._configuration_service is not None:
            queue_size = int(
                self._configuration_service.get(
                    "jobs.queue_size",
                    setting_context_from_execution(submission.execution_context),
                )
            )
            queued = self.repository.list_jobs(
                status=JobStatus.QUEUED,
                limit=queue_size,
                organization_id=context.organization_id if context else None,
                project_id=context.project_id if context else None,
            )
            if len(queued) >= queue_size:
                raise JobSubmissionValidationError(
                    f"Job queue capacity of {queue_size} has been reached."
                )

        now = self._clock()
        job = Job(
            job_id=self._id_generator(),
            job_type=submission.job_type,
            status=JobStatus.QUEUED,
            input_refs=dict(submission.input_refs),
            input_hash=input_hash,
            idempotency_key=submission.idempotency_key,
            submitted_by=submission.submitted_by,
            attempt_count=0,
            max_attempts=submission.max_attempts,
            result_ref=None,
            failure_reason=None,
            leased_by=None,
            lease_expires_at=None,
            heartbeat_at=None,
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
            execution_context=context,
        )
        self.repository.save(job)
        self._publish_job_event("JobQueued", job)
        if self._event_publisher is not None and context is not None:
            asyncio.run(self._event_publisher.publish(ResourceLifecycleEvent(tenant={"organization_id": context.organization_id, "project_id": context.project_id or ""}, resource_kind="job", resource_id=job.job_id, state="queued", payload={"job_type": job.job_type.value})))
        return job

    def get(
        self,
        job_id: str,
    ) -> Job | None:
        """
        Return a submitted job by ID.
        """
        return self.repository.find_by_id(job_id)

    def cancel(
        self,
        job_id: str,
    ) -> None:
        """
        Cancel a submitted job.
        """
        self.repository.cancel(job_id)

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

    @staticmethod
    def _validate(
        submission: JobSubmission,
    ) -> None:
        if not submission.idempotency_key.strip():
            raise JobSubmissionValidationError("idempotency_key is required.")
        if not submission.submitted_by.strip():
            raise JobSubmissionValidationError("submitted_by is required.")
        if not submission.input_refs:
            raise JobSubmissionValidationError("input_refs must not be empty.")
        if not 1 <= submission.max_attempts <= 10:
            raise JobSubmissionValidationError("max_attempts must be between 1 and 10.")


def stable_input_hash(
    input_refs: Mapping[str, Any],
    organization_id: str | None = None,
    project_id: str | None = None,
) -> str:
    """
    Return a stable SHA-256 hash for canonical JSON input references.
    """
    hash_input: Mapping[str, Any]
    if organization_id is None and project_id is None:
        hash_input = input_refs
    else:
        hash_input = {
            "organization_id": organization_id,
            "project_id": project_id,
            "input_refs": dict(input_refs),
        }
    canonical_json = JobPersistenceMapper.canonical_json(hash_input)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def setting_context_from_execution(context) -> Any:
    if context is None:
        return setting_context(None)
    from ai_governance.settings_control.domain import SettingContext

    return SettingContext(context.organization_id, context.project_id)
