"""REST read/write boundary for evidence-fidelity comparisons."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from ai_governance.api.dependencies.evidence_fidelity import (
    get_evidence_fidelity_service,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models.evidence_fidelity import (
    EvidenceFidelityComparisonResponse,
    EvidenceFidelityRequest,
    EvidenceProjectionResponse,
)
from ai_governance.services.evidence_fidelity_service import (
    EvidenceFidelityError,
    EvidenceFidelityService,
)
from ai_governance.tenancy.domain import TenantContext

router = APIRouter(prefix="/api/v1/agents-runtime/evidence-fidelity", tags=["Evidence fidelity"])


@router.post("/comparisons", response_model=EvidenceFidelityComparisonResponse, status_code=status.HTTP_201_CREATED)
def request_comparison(
    body: EvidenceFidelityRequest,
    service: Annotated[EvidenceFidelityService, Depends(get_evidence_fidelity_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> EvidenceFidelityComparisonResponse:
    try:
        return _response(service.request(body.execution_id, context, expected_source_digest=body.expected_source_digest))
    except EvidenceFidelityError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND if error.code == "SOURCE_EXECUTION_UNAVAILABLE" else status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": error.code, "message": str(error)}) from error


@router.get("/comparisons/{comparison_id}", response_model=EvidenceFidelityComparisonResponse)
def get_comparison(
    comparison_id: str,
    service: Annotated[EvidenceFidelityService, Depends(get_evidence_fidelity_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> EvidenceFidelityComparisonResponse:
    try:
        return _response(service.get(comparison_id, context))
    except EvidenceFidelityError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": error.code, "message": str(error)}) from error


@router.get("/executions/{execution_id}/comparisons", response_model=list[EvidenceFidelityComparisonResponse])
def list_execution_comparisons(
    execution_id: str,
    service: Annotated[EvidenceFidelityService, Depends(get_evidence_fidelity_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> list[EvidenceFidelityComparisonResponse]:
    return [_response(item) for item in service.list_for_execution(execution_id, context)]


def _projection(value: Any) -> EvidenceProjectionResponse | None:
    if value is None:
        return None
    return EvidenceProjectionResponse(
        source_execution_id=value.source_execution_id,
        source_artifact_digest=value.source_artifact_digest,
        projection_type=value.projection_type,
        projection_version=value.projection_version,
        projection_fingerprint=value.projection_fingerprint,
        retained_evidence_types=list(value.retained_evidence_types),
        missing_evidence_types=list(value.missing_evidence_types),
        completeness=value.completeness.value,
        event_count=value.event_count,
    )


def _response(value: Any) -> EvidenceFidelityComparisonResponse:
    return EvidenceFidelityComparisonResponse(
        comparison_id=value.comparison_id,
        source_execution_id=value.source_execution_id,
        request_fingerprint=value.request_fingerprint,
        created_at=value.created_at,
        status=value.status.value,
        trajectory=_projection(value.trajectory),
        runtime_projection=_projection(value.runtime_projection),
        outcome_preserved=value.outcome_preserved,
        score_preserved=value.score_preserved,
        token_usage_preserved=value.token_usage_preserved,
        duration_preserved=value.duration_preserved,
        action_count_preserved=value.action_count_preserved,
        ordering_preserved=value.ordering_preserved,
        termination_reason_preserved=value.termination_reason_preserved,
        recovery_sequence_preserved=value.recovery_sequence_preserved,
        failure_classification_preserved=value.failure_classification_preserved,
        causal_evidence_complete=value.causal_evidence_complete,
        trajectory_classification=value.trajectory_classification.value,
        runtime_projection_classification=value.runtime_projection_classification.value,
        retained_evidence_types=list(value.retained_evidence_types),
        missing_evidence_types=list(value.missing_evidence_types),
        unsupported_conclusions=list(value.unsupported_conclusions),
        failure_code=value.failure_code,
        failure_reason=value.failure_reason,
        provenance=dict(value.provenance),
    )
