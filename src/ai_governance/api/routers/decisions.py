from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from ai_governance.api.dependencies.authorization import enforce_permission

from ai_governance.api.dependencies import (
    get_governance_decision_application_service,
)
from ai_governance.api.mappers import DecisionApiMapper
from ai_governance.api.models import (
    DecisionDetailResponse,
    DecisionEvaluateRequest,
    DecisionEvidenceResponse,
    DecisionExplanationResponse,
    DecisionLineageResponse,
    DecisionListResponse,
    DecisionResponse,
    ErrorResponse,
    ReasoningOutcomeResponse,
)
from ai_governance.decisions import DecisionStatus, DecisionTargetType
from ai_governance.services.decision_application_service import (
    DecisionEvaluateCommand,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.tenancy.permissions import Permission

router = APIRouter(
    prefix="/api/v1/decisions",
    tags=["Governance Decisions"],
)


@router.post(
    "/evaluate",
    response_model=ReasoningOutcomeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Evaluate governance decision",
    description="Evaluate and persist a deterministic governance decision.",
)
def evaluate_decision(
    request: DecisionEvaluateRequest,
    service: Annotated[
        object,
        Depends(get_governance_decision_application_service),
    ],
    context=Depends(get_compatible_tenant_context),
    _=Depends(enforce_permission(Permission.DECISION_EVALUATE)),
) -> ReasoningOutcomeResponse:
    return DecisionApiMapper.to_reasoning_outcome_response(
        service.evaluate(
            DecisionEvaluateCommand(
                target_type=request.target_type,
                target_id=request.target_id,
                decision_type=request.decision_type,
                policy_ids=tuple(request.policy_ids),
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                metadata={
                    **request.metadata,
                    "_organization_id": context.organization_id,
                    "_project_id": context.project_id,
                },
                context=context,
            )
        )
    )


@router.get(
    "",
    response_model=DecisionListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="List governance decisions",
    description="List decisions with optional target, status, and correlation filters.",
)
def list_decisions(
    service: Annotated[
        object,
        Depends(get_governance_decision_application_service),
    ],
    target_type: DecisionTargetType | None = None,
    target_id: str | None = None,
    status: DecisionStatus | None = None,
    correlation_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    context=Depends(get_compatible_tenant_context),
) -> DecisionListResponse:
    return DecisionApiMapper.to_list_response(
        service.list(
            target_type=target_type,
            target_id=target_id,
            status=status,
            correlation_id=correlation_id,
            limit=limit,
            context=context,
        )
    )


@router.get(
    "/{decision_id}",
    response_model=DecisionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get governance decision",
    description="Return a persisted governance decision.",
)
def get_decision(
    decision_id: str,
    service: Annotated[
        object,
        Depends(get_governance_decision_application_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> DecisionResponse:
    return DecisionApiMapper.to_decision_response(service.get(decision_id, context))


@router.get(
    "/{decision_id}/detail",
    response_model=DecisionDetailResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get governance decision detail",
    description=(
        "Return the persisted decision with stored evidence summary, policy "
        "outcomes, and audit records for console inspection."
    ),
)
def get_decision_detail(
    decision_id: str,
    service: Annotated[
        object,
        Depends(get_governance_decision_application_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> DecisionDetailResponse:
    return DecisionApiMapper.to_detail_response(service.detail(decision_id, context))


@router.get(
    "/{decision_id}/evidence",
    response_model=DecisionEvidenceResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get decision evidence",
    description="Return persisted evidence references and rebuilt evidence graph.",
)
def get_decision_evidence(
    decision_id: str,
    service: Annotated[
        object,
        Depends(get_governance_decision_application_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> DecisionEvidenceResponse:
    return DecisionApiMapper.to_evidence_response(
        service.evidence(decision_id, context)
    )


@router.get(
    "/{decision_id}/explanation",
    response_model=DecisionExplanationResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get decision explanation",
    description="Return the persisted deterministic decision explanation.",
)
def get_decision_explanation(
    decision_id: str,
    service: Annotated[
        object,
        Depends(get_governance_decision_application_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> DecisionExplanationResponse:
    return DecisionApiMapper.to_explanation_response(
        service.explanation(decision_id, context)
    )


@router.get(
    "/{decision_id}/lineage",
    response_model=DecisionLineageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get decision lineage",
    description="Return ontology subgraph lineage around the governance decision.",
)
def get_decision_lineage(
    decision_id: str,
    service: Annotated[
        object,
        Depends(get_governance_decision_application_service),
    ],
    depth: int = Query(default=2, ge=1, le=5),
    context=Depends(get_compatible_tenant_context),
) -> DecisionLineageResponse:
    return DecisionApiMapper.to_lineage_response(
        service.lineage(decision_id, depth=depth, context=context)
    )
