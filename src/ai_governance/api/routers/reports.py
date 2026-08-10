from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from ai_governance.api.dependencies import get_governance_report_service
from ai_governance.api.mappers import GovernanceInsightApiMapper
from ai_governance.api.models import (
    ErrorResponse,
    GovernanceEvidenceReportResponse,
)

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["Reports"],
)

ReportFormat = Literal["json", "markdown"]


@router.get(
    "/experiments/{experiment_id}",
    response_model=GovernanceEvidenceReportResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Generate experiment report",
    description="Generate an evidence report for an experiment.",
)
def generate_experiment_report(
    experiment_id: str,
    report_service: Annotated[
        object,
        Depends(get_governance_report_service),
    ],
    format: ReportFormat = Query(default="json"),  # noqa: A002
) -> GovernanceEvidenceReportResponse:
    return GovernanceInsightApiMapper.to_report_response(
        report_service.experiment_report(experiment_id, format)
    )


@router.get(
    "/evaluations/{evaluation_id}",
    response_model=GovernanceEvidenceReportResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Generate evaluation report",
    description="Generate an evidence report for an evaluation.",
)
def generate_evaluation_report(
    evaluation_id: str,
    report_service: Annotated[
        object,
        Depends(get_governance_report_service),
    ],
    format: ReportFormat = Query(default="json"),  # noqa: A002
) -> GovernanceEvidenceReportResponse:
    return GovernanceInsightApiMapper.to_report_response(
        report_service.evaluation_report(evaluation_id, format)
    )


@router.get(
    "/drift/{drift_id}",
    response_model=GovernanceEvidenceReportResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Generate drift report",
    description="Generate an evidence report for a drift identifier.",
)
def generate_drift_report(
    drift_id: str,
    report_service: Annotated[
        object,
        Depends(get_governance_report_service),
    ],
    format: ReportFormat = Query(default="json"),  # noqa: A002
) -> GovernanceEvidenceReportResponse:
    return GovernanceInsightApiMapper.to_report_response(
        report_service.drift_report(drift_id, format)
    )


@router.get(
    "/investigations/{correlation_id}",
    response_model=GovernanceEvidenceReportResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Generate investigation report",
    description="Generate an evidence report for an execution correlation ID.",
)
def generate_investigation_report(
    correlation_id: str,
    report_service: Annotated[
        object,
        Depends(get_governance_report_service),
    ],
    format: ReportFormat = Query(default="json"),  # noqa: A002
) -> GovernanceEvidenceReportResponse:
    return GovernanceInsightApiMapper.to_report_response(
        report_service.investigation_report(correlation_id, format)
    )


@router.get(
    "/mcp-audit/{audit_id}",
    response_model=GovernanceEvidenceReportResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Generate MCP audit report",
    description="Generate an evidence report for an MCP audit record.",
)
def generate_mcp_audit_report(
    audit_id: str,
    report_service: Annotated[
        object,
        Depends(get_governance_report_service),
    ],
    format: ReportFormat = Query(default="json"),  # noqa: A002
) -> GovernanceEvidenceReportResponse:
    return GovernanceInsightApiMapper.to_report_response(
        report_service.mcp_audit_report(audit_id, format)
    )
