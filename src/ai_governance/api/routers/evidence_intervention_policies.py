"""REST adapter for versioned Evidence Intervention Policies."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from ai_governance.api.dependencies.agent_execution import (
    get_agent_execution_repository,
)
from ai_governance.api.dependencies.evidence_intervention_policy import (
    get_evidence_intervention_policy_service,
    get_governed_counterfactual_generator,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models.evidence_intervention_policy import (
    EvidenceInterventionPolicyCreateRequest,
    EvidenceInterventionPolicyEditRequest,
    EvidenceInterventionPolicyListResponse,
    EvidenceInterventionPolicyPreviewRequest,
    EvidenceInterventionPolicyPreviewResponse,
    EvidenceInterventionPolicyResponse,
)
from ai_governance.domain.replay import ControlledEvidenceStrategy
from ai_governance.services.evidence_intervention_policy_service import (
    EvidenceInterventionPolicyService,
    InterventionPolicyAmbiguous,
    InterventionPolicyNotFound,
)
from ai_governance.tenancy.domain import TenantContext

router = APIRouter(
    prefix="/api/v1/agents-runtime/causal-audit/intervention-policies",
    tags=["Causal audit intervention policies"],
)


@router.post(
    "",
    response_model=EvidenceInterventionPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_policy(
    body: EvidenceInterventionPolicyCreateRequest,
    service: Annotated[
        EvidenceInterventionPolicyService,
        Depends(get_evidence_intervention_policy_service),
    ],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> EvidenceInterventionPolicyResponse:
    try:
        policy = service.create_draft(
            tool_name=body.tool_name,
            schema_id=body.schema_id,
            schema_version=body.schema_version,
            provider_id=body.provider_id,
            provider_version=body.provider_version,
            allowed_strategies=tuple(
                ControlledEvidenceStrategy(item) for item in body.allowed_strategies
            ),
            strategy_configuration=body.strategy_configuration,
            context=context,
        )
        return _response(policy)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.get("", response_model=EvidenceInterventionPolicyListResponse)
def list_policies(
    service: Annotated[
        EvidenceInterventionPolicyService,
        Depends(get_evidence_intervention_policy_service),
    ],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> EvidenceInterventionPolicyListResponse:
    return EvidenceInterventionPolicyListResponse(
        items=[_response(item) for item in service.list(context)]
    )


@router.get("/{policy_id}", response_model=EvidenceInterventionPolicyListResponse)
def list_policy_versions(
    policy_id: str,
    service: Annotated[
        EvidenceInterventionPolicyService,
        Depends(get_evidence_intervention_policy_service),
    ],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> EvidenceInterventionPolicyListResponse:
    try:
        return EvidenceInterventionPolicyListResponse(
            items=[
                _response(item) for item in service.list_versions(policy_id, context)
            ]
        )
    except InterventionPolicyNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.get(
    "/{policy_id}/versions/{version}", response_model=EvidenceInterventionPolicyResponse
)
def get_policy(
    policy_id: str,
    version: int,
    service: Annotated[
        EvidenceInterventionPolicyService,
        Depends(get_evidence_intervention_policy_service),
    ],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> EvidenceInterventionPolicyResponse:
    return _operation(lambda: service.get(policy_id, version, context))


@router.post(
    "/{policy_id}/versions/{version}/edit",
    response_model=EvidenceInterventionPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
def edit_active_policy(
    policy_id: str,
    version: int,
    body: EvidenceInterventionPolicyEditRequest,
    service: Annotated[
        EvidenceInterventionPolicyService,
        Depends(get_evidence_intervention_policy_service),
    ],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> EvidenceInterventionPolicyResponse:
    return _operation(
        lambda: service.create_next_draft(
            policy_id, version, body.strategy_configuration, context
        )
    )


@router.post(
    "/{policy_id}/versions/{version}/validate",
    response_model=EvidenceInterventionPolicyResponse,
)
def validate_policy(
    policy_id: str,
    version: int,
    service: Annotated[
        EvidenceInterventionPolicyService,
        Depends(get_evidence_intervention_policy_service),
    ],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> EvidenceInterventionPolicyResponse:
    return _operation(lambda: service.validate(policy_id, version, context))


@router.post(
    "/{policy_id}/versions/{version}/activate",
    response_model=EvidenceInterventionPolicyResponse,
)
def activate_policy(
    policy_id: str,
    version: int,
    service: Annotated[
        EvidenceInterventionPolicyService,
        Depends(get_evidence_intervention_policy_service),
    ],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> EvidenceInterventionPolicyResponse:
    return _operation(lambda: service.activate(policy_id, version, context))


@router.post(
    "/{policy_id}/versions/{version}/retire",
    response_model=EvidenceInterventionPolicyResponse,
)
def retire_policy(
    policy_id: str,
    version: int,
    service: Annotated[
        EvidenceInterventionPolicyService,
        Depends(get_evidence_intervention_policy_service),
    ],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> EvidenceInterventionPolicyResponse:
    return _operation(lambda: service.retire(policy_id, version, context))


@router.post(
    "/{policy_id}/versions/{version}/preview",
    response_model=EvidenceInterventionPolicyPreviewResponse,
)
def preview_policy(
    policy_id: str,
    version: int,
    body: EvidenceInterventionPolicyPreviewRequest,
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> EvidenceInterventionPolicyPreviewResponse:
    """Generate and validate a safe counterfactual preview without creating Replay."""
    from ai_governance.domain.agent_execution import EventType

    events = get_agent_execution_repository().event.list_by_execution(
        body.execution_id, context.organization_id, context.project_id
    )
    event = next(
        (
            item
            for item in events
            if item.event_id == body.tool_call_id
            and item.event_type is EventType.TOOL_CALL
        ),
        None,
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eligible tool-call evidence was not found in the current scope.",
        )
    try:
        result = get_governed_counterfactual_generator().generate(
            event,
            ControlledEvidenceStrategy(body.strategy),
            policy_id,
            version,
            body.seed,
            context,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    return EvidenceInterventionPolicyPreviewResponse(
        strategy=result.strategy.value,
        policy_id=result.policy_id,
        policy_version=result.policy_version,
        provider_id=result.provider_id,
        provider_version=result.provider_version,
        seed=result.seed,
        original_evidence_digest=result.original_evidence_digest,
        counterfactual_evidence_ref=result.counterfactual_evidence_ref,
        counterfactual_evidence_digest=result.counterfactual_evidence_digest,
        schema_valid=result.schema_valid,
        semantic_valid=result.semantic_valid,
        material_difference=True,
        generation_metadata=dict(result.generation_metadata),
    )


def _operation(callback) -> EvidenceInterventionPolicyResponse:
    try:
        return _response(callback())
    except InterventionPolicyNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except InterventionPolicyAmbiguous as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


def _response(policy: Any) -> EvidenceInterventionPolicyResponse:
    return EvidenceInterventionPolicyResponse(
        policy_id=policy.policy_id,
        version=policy.version,
        status=policy.status.value,
        tool_name=policy.tool_name,
        schema_id=policy.schema_id,
        schema_version=policy.schema_version,
        provider_id=policy.provider_id,
        provider_version=policy.provider_version,
        allowed_strategies=[item.value for item in policy.allowed_strategies],
        strategy_configuration=dict(policy.strategy_configuration),
        policy_digest=policy.policy_digest,
        created_at=policy.created_at,
        created_by=policy.created_by,
        activated_at=policy.activated_at,
        activated_by=policy.activated_by,
        retired_at=policy.retired_at,
    )
