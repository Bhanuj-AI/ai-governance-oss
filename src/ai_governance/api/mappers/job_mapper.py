from __future__ import annotations

from typing import final

from ai_governance.api.models import (
    JobListResponse,
    JobResponse,
    JobResultResponse,
    JobSubmitRequest,
)
from ai_governance.domain.jobs import Job, JobExecutionContext, JobSubmission
from ai_governance.tenancy.domain import TenantContext


@final
class JobApiMapper:
    """
    Maps job REST DTOs to and from domain objects.
    """

    @staticmethod
    def to_submission(
        request: JobSubmitRequest,
        context: TenantContext | None = None,
    ) -> JobSubmission:
        """
        Convert a REST submission request into a domain submission.
        """
        return JobSubmission(
            job_type=request.job_type,
            input_refs=dict(request.input_refs),
            idempotency_key=request.idempotency_key,
            submitted_by=request.submitted_by,
            max_attempts=request.max_attempts,
            execution_context=(
                JobExecutionContext(
                    context.organization_id,
                    context.project_id or "",
                    context.actor_id,
                    context.request_id,
                    context.correlation_id,
                )
                if context is not None and context.project_id is not None
                else None
            ),
        )

    @staticmethod
    def to_response(
        job: Job,
    ) -> JobResponse:
        """
        Convert a domain job into the public REST response shape.
        """
        return JobResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            input_refs=dict(job.input_refs),
            input_hash=job.input_hash,
            idempotency_key=job.idempotency_key,
            submitted_by=job.submitted_by,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            result_ref=job.result_ref,
            failure_reason=job.failure_reason,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )

    @staticmethod
    def to_list_response(
        jobs: list[Job],
    ) -> JobListResponse:
        """
        Convert a list of jobs into the public list response shape.
        """
        return JobListResponse(
            jobs=[JobApiMapper.to_response(job) for job in jobs],
        )

    @staticmethod
    def to_result_response(
        job: Job,
    ) -> JobResultResponse:
        """
        Convert a job into the public result reference response shape.
        """
        return JobResultResponse(
            job_id=job.job_id,
            status=job.status,
            result_ref=job.result_ref,
            failure_reason=job.failure_reason,
        )
