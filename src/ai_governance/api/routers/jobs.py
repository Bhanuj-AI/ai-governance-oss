from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status

from ai_governance.api.dependencies import get_job_api_service
from ai_governance.api.dependencies.settings_control import get_configuration_service
from ai_governance.api.dependencies.tenancy import (
    get_compatible_tenant_context,
    get_control_plane_service,
)
from ai_governance.api.mappers import JobApiMapper
from ai_governance.api.models import (
    ErrorResponse,
    JobListResponse,
    JobResponse,
    JobResultResponse,
    JobSubmitRequest,
)
from ai_governance.domain.jobs import JobStatus, JobType
from ai_governance.settings_control.operational import setting_context
from ai_governance.tenancy.permissions import Permission

router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["Jobs"],
)


@router.post(
    "",
    response_model=JobResponse,
    status_code=http_status.HTTP_201_CREATED,
    responses={
        http_status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        http_status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Submit job",
    description="Submit an asynchronous governance job.",
)
def submit_job(
    request: JobSubmitRequest,
    job_api_service: Annotated[
        object,
        Depends(get_job_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
    control_plane=Depends(get_control_plane_service),
    configuration_service=Depends(get_configuration_service),
) -> JobResponse:
    """
    Submit a new job or return an existing idempotent job.
    """
    control_plane.require(context, Permission.JOB_SUBMIT)
    if "max_attempts" not in request.model_fields_set:
        request = request.model_copy(
            update={
                "max_attempts": int(
                    configuration_service.get(
                        "jobs.retry_attempts", setting_context(context)
                    )
                )
            }
        )
    job = job_api_service.submit(JobApiMapper.to_submission(request, context))
    return JobApiMapper.to_response(job)


@router.get(
    "",
    response_model=JobListResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="List jobs",
    description="List jobs with optional status and type filters.",
)
def list_jobs(
    job_api_service: Annotated[
        object,
        Depends(get_job_api_service),
    ],
    status: JobStatus | None = None,
    job_type: JobType | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    context=Depends(get_compatible_tenant_context),
    control_plane=Depends(get_control_plane_service),
) -> JobListResponse:
    """
    Return jobs filtered by optional status and type.
    """
    control_plane.require(context, Permission.JOB_READ)
    return JobApiMapper.to_list_response(
        job_api_service.list_jobs(
            status=status,
            job_type=job_type,
            limit=limit,
            context=context,
        )
    )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get job",
    description="Return job status and metadata.",
)
def get_job(
    job_id: str,
    job_api_service: Annotated[
        object,
        Depends(get_job_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
    control_plane=Depends(get_control_plane_service),
) -> JobResponse:
    """
    Return a job by ID.
    """
    control_plane.require(context, Permission.JOB_READ)
    return JobApiMapper.to_response(job_api_service.get(job_id, context))


@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        http_status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Cancel job",
    description="Cancel a queued job, or best-effort cancel a running job.",
)
def cancel_job(
    job_id: str,
    job_api_service: Annotated[
        object,
        Depends(get_job_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
    control_plane=Depends(get_control_plane_service),
) -> JobResponse:
    """
    Cancel a queued or running job.
    """
    control_plane.require(context, Permission.JOB_CANCEL)
    return JobApiMapper.to_response(job_api_service.cancel(job_id, context))


@router.post(
    "/{job_id}/retry",
    response_model=JobResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        http_status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Retry job",
    description="Requeue or recreate a failed job using the same input refs.",
)
def retry_job(
    job_id: str,
    job_api_service: Annotated[
        object,
        Depends(get_job_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
    control_plane=Depends(get_control_plane_service),
) -> JobResponse:
    """
    Retry a failed job using the same input refs.
    """
    control_plane.require(context, Permission.JOB_RETRY)
    return JobApiMapper.to_response(job_api_service.retry(job_id, context))


@router.get(
    "/{job_id}/result",
    response_model=JobResultResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get job result",
    description="Return the job result reference and current status.",
)
def get_job_result(
    job_id: str,
    job_api_service: Annotated[
        object,
        Depends(get_job_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
    control_plane=Depends(get_control_plane_service),
) -> JobResultResponse:
    """
    Return the immutable result reference when available.
    """
    control_plane.require(context, Permission.JOB_READ)
    return JobApiMapper.to_result_response(job_api_service.get_result(job_id, context))
