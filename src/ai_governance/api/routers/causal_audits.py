"""Causal Audit REST adapter over the Agents Runtime application service."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ai_governance.api.dependencies.authorization import enforce_permission
from ai_governance.api.dependencies.causal_audit import (
    causal_audit_list_filters,
    get_causal_audit_service,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models.causal_audit import (
    CausalAuditCreateRequest,
    CausalAuditEligibilityResponse,
    CausalAuditListResponse,
    CausalAuditResponse,
    CounterfactualReplayLineageResponse,
    OutcomeScoreResponse,
    ToolEvidenceInfluenceResponse,
)
from ai_governance.domain.causal_audit import (
    CausalAuditClassification,
    CausalAuditStatus,
    EvidenceInterventionStrategy,
    InterventionConfiguration,
)
from ai_governance.services.causal_audit_service import (
    CausalAuditNotFound,
    CausalAuditService,
)
from ai_governance.tenancy.domain import TenantContext
from ai_governance.tenancy.permissions import Permission

router = APIRouter(prefix="/api/v1/agents-runtime", tags=["Causal audits"])


@router.post(
    "/causal-audits",
    response_model=CausalAuditResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a causal audit for an execution",
)
def create_causal_audit(
    body: CausalAuditCreateRequest,
    service: Annotated[CausalAuditService, Depends(get_causal_audit_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    _: object = Depends(enforce_permission(Permission.CAUSAL_AUDIT_CREATE)),
) -> CausalAuditResponse:
    try:
        intervention = InterventionConfiguration(
            EvidenceInterventionStrategy(body.intervention.strategy),
            body.intervention.counterfactual_samples,
            seed=body.intervention.seed,
            configuration=body.intervention.configuration,
            intervention_policy_id=body.intervention.intervention_policy_id,
            intervention_policy_version=body.intervention.intervention_policy_version,
        )
        return _audit_response(
            service.start(body.execution_id, body.evaluator_ref, intervention, context)
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.get(
    "/causal-audits",
    response_model=CausalAuditListResponse,
    summary="List causal audits",
)
def list_causal_audits(
    service: Annotated[CausalAuditService, Depends(get_causal_audit_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    _: object = Depends(enforce_permission(Permission.CAUSAL_AUDIT_READ)),
    agent_id: str | None = Query(None),
    classification: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    evaluator_ref: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> CausalAuditListResponse:
    try:
        filters = causal_audit_list_filters(
            agent_id=agent_id,
            classification=CausalAuditClassification(classification)
            if classification
            else None,
            status=CausalAuditStatus(status_filter) if status_filter else None,
            evaluator_ref=evaluator_ref,
            offset=offset,
            limit=limit + 1,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error
    audits = service.list(context, filters)
    return CausalAuditListResponse(
        items=[_audit_response(audit) for audit in audits[:limit]],
        next_offset=offset + limit if len(audits) > limit else None,
    )


@router.get(
    "/causal-audits/{audit_id}",
    response_model=CausalAuditResponse,
    summary="Get a causal audit",
)
def get_causal_audit(
    audit_id: str,
    service: Annotated[CausalAuditService, Depends(get_causal_audit_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    _: object = Depends(enforce_permission(Permission.CAUSAL_AUDIT_READ)),
) -> CausalAuditResponse:
    try:
        return _audit_response(service.get(audit_id, context))
    except CausalAuditNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.get(
    "/executions/{execution_id}/causal-audits",
    response_model=CausalAuditListResponse,
    summary="List causal audits for an execution",
)
def list_execution_causal_audits(
    execution_id: str,
    service: Annotated[CausalAuditService, Depends(get_causal_audit_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    _: object = Depends(enforce_permission(Permission.CAUSAL_AUDIT_READ)),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> CausalAuditListResponse:
    audits = service.list(
        context, causal_audit_list_filters(offset=offset, limit=limit + 1), execution_id
    )
    return CausalAuditListResponse(
        items=[_audit_response(audit) for audit in audits[:limit]],
        next_offset=offset + limit if len(audits) > limit else None,
    )


@router.get(
    "/executions/{execution_id}/causal-audit-eligibility",
    response_model=CausalAuditEligibilityResponse,
    summary="Check whether an execution can be safely causally audited",
)
def causal_audit_eligibility(
    execution_id: str,
    service: Annotated[CausalAuditService, Depends(get_causal_audit_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    _: object = Depends(enforce_permission(Permission.CAUSAL_AUDIT_READ)),
    evaluator_ref: str = Query("recorded-outcome/v1"),
    intervention_policy_id: str | None = Query(None, min_length=1),
    intervention_policy_version: int | None = Query(None, ge=1),
) -> CausalAuditEligibilityResponse:
    result = service.eligibility(
        execution_id,
        context,
        evaluator_ref,
        intervention_policy_id=intervention_policy_id,
        intervention_policy_version=intervention_policy_version,
    )
    return CausalAuditEligibilityResponse(
        code=result.code.value,
        reason=result.reason,
        auditable_tool_call_count=result.auditable_tool_call_count,
    )


def _score_response(score: Any) -> OutcomeScoreResponse:
    return OutcomeScoreResponse(
        value=score.value,
        method=score.method,
        provider=score.provider,
        evaluator_version=score.evaluator_version,
        metadata=dict(score.metadata),
    )


def _audit_response(audit: Any) -> CausalAuditResponse:
    return CausalAuditResponse(
        audit_id=audit.audit_id,
        execution_id=audit.execution_id,
        agent_id=audit.agent_id,
        status=audit.status.value,
        methodology_version=audit.methodology_version,
        evaluator_ref=audit.evaluator_ref,
        intervention_strategy=audit.intervention.strategy.value,
        counterfactual_samples=audit.intervention.counterfactual_samples,
        intervention_policy_id=audit.intervention.intervention_policy_id,
        intervention_policy_version=audit.intervention.intervention_policy_version,
        classification=audit.classification.value if audit.classification else None,
        failure_code=audit.failure_code,
        failure_reason=audit.failure_reason,
        created_at=audit.created_at,
        started_at=audit.started_at,
        completed_at=audit.completed_at,
        diagnostics=dict(audit.diagnostics),
        tool_call_results=[
            ToolEvidenceInfluenceResponse(
                tool_call_id=item.tool_call_id,
                tool_name=item.tool_name,
                position=item.position,
                intervention_strategy=item.intervention.strategy.value,
                intervention_strategy_version=item.intervention.strategy_version,
                intervention_seed=item.intervention.seed,
                counterfactual_count=item.counterfactual_count,
                baseline_score=_score_response(item.baseline_score),
                counterfactual_score=_score_response(item.counterfactual_score),
                influence_score=item.influence_score,
                useful=item.useful,
                harmful=item.harmful,
                post_saturation=item.post_saturation,
                counterfactual_replay_ids=list(item.counterfactual_replay_ids),
                counterfactual_execution_ids=list(item.counterfactual_execution_ids),
                evidence_references=list(item.evidence_references),
                intervention_provenance=dict(
                    item.diagnostics.get("intervention_provenance", {})
                ),
                diagnostics=dict(item.diagnostics),
                counterfactual_lineage=[
                    CounterfactualReplayLineageResponse(
                        replay_id=lineage.replay_id,
                        replay_execution_id=lineage.replay_execution_id,
                        replay_status=lineage.replay_status,
                        policy_id=lineage.policy_id,
                        policy_version=lineage.policy_version,
                        provider_id=lineage.provider_id,
                        provider_version=lineage.provider_version,
                        original_evidence_digest=lineage.original_evidence_digest,
                        counterfactual_evidence_reference=lineage.counterfactual_evidence_reference,
                        counterfactual_evidence_digest=lineage.counterfactual_evidence_digest,
                        intervention_digest=lineage.intervention_digest,
                        evaluator_score=_score_response(lineage.evaluator_score),
                    )
                    for lineage in item.counterfactual_lineage
                ],
            )
            for item in audit.tool_call_results
        ],
    )
