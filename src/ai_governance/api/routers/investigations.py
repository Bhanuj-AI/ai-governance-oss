from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from ai_governance.api.dependencies import get_execution_investigation_service
from ai_governance.api.mappers import GovernanceInsightApiMapper
from ai_governance.api.models import ErrorResponse, GovernanceInsightResponse

router = APIRouter(
    prefix="/api/v1/investigations",
    tags=["Investigations"],
)


@router.get(
    "/by-correlation/{correlation_id}",
    response_model=GovernanceInsightResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Investigate by correlation",
    description="Correlate audit, job, and evaluation evidence by correlation ID.",
)
def investigate_by_correlation(
    correlation_id: str,
    investigation_service: Annotated[
        object,
        Depends(get_execution_investigation_service),
    ],
) -> GovernanceInsightResponse:
    """
    Return execution investigation evidence by correlation ID.
    """
    return GovernanceInsightApiMapper.to_insight_response(
        investigation_service.by_correlation(correlation_id)
    )


@router.get(
    "/by-job/{job_id}",
    response_model=GovernanceInsightResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Investigate by job",
    description="Correlate audit and evaluation evidence by job ID.",
)
def investigate_by_job(
    job_id: str,
    investigation_service: Annotated[
        object,
        Depends(get_execution_investigation_service),
    ],
) -> GovernanceInsightResponse:
    """
    Return execution investigation evidence by job ID.
    """
    return GovernanceInsightApiMapper.to_insight_response(
        investigation_service.by_job(job_id)
    )


@router.get(
    "/by-evaluation/{evaluation_id}",
    response_model=GovernanceInsightResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Investigate by evaluation",
    description="Correlate job and audit evidence by evaluation ID.",
)
def investigate_by_evaluation(
    evaluation_id: str,
    investigation_service: Annotated[
        object,
        Depends(get_execution_investigation_service),
    ],
) -> GovernanceInsightResponse:
    """
    Return execution investigation evidence by evaluation ID.
    """
    return GovernanceInsightApiMapper.to_insight_response(
        investigation_service.by_evaluation(evaluation_id)
    )


@router.get(
    "/by-audit/{audit_id}",
    response_model=GovernanceInsightResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Investigate by audit",
    description="Correlate job and evaluation evidence by MCP audit ID.",
)
def investigate_by_audit(
    audit_id: str,
    investigation_service: Annotated[
        object,
        Depends(get_execution_investigation_service),
    ],
) -> GovernanceInsightResponse:
    """
    Return execution investigation evidence by MCP audit ID.
    """
    return GovernanceInsightApiMapper.to_insight_response(
        investigation_service.by_audit(audit_id)
    )
