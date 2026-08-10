from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from ai_governance.api.dependencies import get_drift_explanation_service
from ai_governance.api.dependencies import get_governance_api_service
from ai_governance.api.mappers import GovernanceApiMapper
from ai_governance.api.mappers import GovernanceInsightApiMapper
from ai_governance.api.models import (
    DriftAnalysisRequest,
    DriftAnalysisResponse,
    ErrorResponse,
    EvaluationComparisonRequest,
    EvaluationComparisonResponse,
    GovernanceInsightResponse,
    GovernanceReportResponse,
)

router = APIRouter(
    prefix="/api/v1/governance",
    tags=["Governance"],
)


@router.post(
    "/compare",
    response_model=EvaluationComparisonResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Compare evaluations",
    description="Compare metrics between two persisted evaluations.",
)
def compare_evaluations(
    request: EvaluationComparisonRequest,
    governance_api_service: Annotated[
        object,
        Depends(get_governance_api_service),
    ],
) -> EvaluationComparisonResponse:
    """
    Compare metrics between two persisted evaluations.
    """
    return GovernanceApiMapper.to_comparison_response(
        governance_api_service.compare_evaluations(
            baseline_evaluation_id=request.baseline_evaluation_id,
            candidate_evaluation_id=request.candidate_evaluation_id,
        )
    )


@router.post(
    "/drift",
    response_model=DriftAnalysisResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Analyze drift",
    description="Analyze governance drift between two persisted evaluations.",
)
def analyze_drift(
    request: DriftAnalysisRequest,
    governance_api_service: Annotated[
        object,
        Depends(get_governance_api_service),
    ],
) -> DriftAnalysisResponse:
    """
    Analyze governance drift between two persisted evaluations.
    """
    return GovernanceApiMapper.to_drift_response(
        governance_api_service.analyze_drift(
            baseline_evaluation_id=request.baseline_evaluation_id,
            candidate_evaluation_id=request.candidate_evaluation_id,
        )
    )


@router.get(
    "/drift/{drift_id}/explanation",
    response_model=GovernanceInsightResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Explain drift",
    description="Explain existing governance drift evidence.",
)
def explain_drift(
    drift_id: str,
    drift_explanation_service: Annotated[
        object,
        Depends(get_drift_explanation_service),
    ],
) -> GovernanceInsightResponse:
    """
    Return a structured explanation for a drift identifier.
    """
    return GovernanceInsightApiMapper.to_insight_response(
        drift_explanation_service.explain_drift(drift_id)
    )


@router.get(
    "/reports/{evaluation_id}",
    response_model=GovernanceReportResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_501_NOT_IMPLEMENTED: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get governance report",
    description="Return a governance report if report generation is configured.",
)
def get_governance_report(
    evaluation_id: str,
    governance_api_service: Annotated[
        object,
        Depends(get_governance_api_service),
    ],
) -> GovernanceReportResponse:
    """
    Return a governance report if report generation is configured.
    """
    governance_api_service.get_report(evaluation_id)
    return GovernanceReportResponse(evaluation_id=evaluation_id)
