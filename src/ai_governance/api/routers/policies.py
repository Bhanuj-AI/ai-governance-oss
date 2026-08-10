from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from ai_governance.api.dependencies import get_policy_administration_service
from ai_governance.api.models import (
    ActivatePolicyVersionRequest,
    ArchivePolicyVersionRequest,
    CreatePolicyRequest,
    CreatePolicyRuleRequest,
    CreatePolicyVersionRequest,
    ErrorResponse,
    PolicyDetailResponse,
    PolicyListItemResponse,
    PolicySchemaResponse,
    PolicySimulationRequest,
    PolicySimulationResponse,
    PolicyVersionResponse,
    UpdateDraftPolicyVersionRequest,
)
from ai_governance.decisions import PolicyRule
from ai_governance.services.policies import build_policy_rule
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context

router = APIRouter(
    tags=["Policies"],
)


@router.get(
    "/api/v1/policy-schema",
    response_model=PolicySchemaResponse,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse}},
    summary="Get policy schema",
    description="Return backend-owned policy authoring schema metadata.",
)
def get_policy_schema(
    policy_service: Annotated[
        object,
        Depends(get_policy_administration_service),
    ],
) -> PolicySchemaResponse:
    return PolicySchemaResponse.from_domain(policy_service.get_policy_schema())


@router.get(
    "/api/v1/policies",
    response_model=list[PolicyListItemResponse],
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse}},
    summary="List policies",
    description="Return Studio-ready policy summaries.",
)
def list_policies(
    policy_service: Annotated[
        object,
        Depends(get_policy_administration_service),
    ],
    organization_id: str | None = None,
    project_id: str | None = None,
    search: str | None = None,
    owner: str | None = None,
    category: str | None = None,
    policy_status: str | None = Query(default=None, alias="status"),
    target_type: str | None = None,
    effect: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    context=Depends(get_compatible_tenant_context),
) -> list[PolicyListItemResponse]:
    return [
        PolicyListItemResponse.from_domain(item)
        for item in policy_service.list_policies(
            organization_id=context.organization_id,
            project_id=context.project_id,
            search=search,
            owner=owner,
            category=category,
            status=policy_status,
            target_type=target_type,
            effect=effect,
            limit=limit,
            offset=offset,
        )
    ]


@router.post(
    "/api/v1/policies",
    response_model=PolicyDetailResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Create policy",
    description="Create a policy definition and initial draft version.",
)
def create_policy(
    request: CreatePolicyRequest,
    policy_service: Annotated[
        object,
        Depends(get_policy_administration_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> PolicyDetailResponse:
    return PolicyDetailResponse.from_domain(
        policy_service.create_policy(
            name=request.name,
            description=request.description,
            organization_id=context.organization_id,
            project_id=context.project_id,
            category=request.category,
            owner=request.owner,
            created_by=request.created_by,
            target_types=request.target_types,
            rules=_rules(request.rules),
            metadata=request.metadata,
        )
    )


@router.get(
    "/api/v1/policies/{policy_id}",
    response_model=PolicyDetailResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get policy detail",
    description="Return one policy definition with draft, active, and versions.",
)
def get_policy(
    policy_id: str,
    policy_service: Annotated[
        object,
        Depends(get_policy_administration_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> PolicyDetailResponse:
    # Resolve the same tenant context used by the inventory endpoint.  The
    # detail request must not rely on a repository-wide lookup because a
    # policy can only be addressed inside the selected organization/project.
    detail = policy_service.get_policy_detail(policy_id.strip())
    if (
        detail.organization_id != context.organization_id
        or detail.project_id != context.project_id
    ):
        from ai_governance.services.policies import PolicyAdminNotFoundError

        raise PolicyAdminNotFoundError(
            f"Policy '{policy_id}' does not exist."
        )
    return PolicyDetailResponse.from_domain(detail)


@router.post(
    "/api/v1/policies/{policy_id}/versions",
    response_model=PolicyDetailResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Create policy version",
    description="Create a new draft policy version.",
)
def create_policy_version(
    policy_id: str,
    request: CreatePolicyVersionRequest,
    policy_service: Annotated[
        object,
        Depends(get_policy_administration_service),
    ],
) -> PolicyDetailResponse:
    return PolicyDetailResponse.from_domain(
        policy_service.create_policy_version(
            policy_id=policy_id,
            base_version=request.base_version,
            target_types=request.target_types,
            rules=_rules(request.rules),
            created_by=request.created_by,
            metadata=request.metadata,
        )
    )


@router.get(
    "/api/v1/policies/{policy_id}/versions/{version}",
    response_model=PolicyVersionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get policy version",
    description="Return executable content for one policy version.",
)
def get_policy_version(
    policy_id: str,
    version: str,
    policy_service: Annotated[
        object,
        Depends(get_policy_administration_service),
    ],
) -> PolicyVersionResponse:
    return PolicyVersionResponse.from_domain(
        policy_service.get_policy_version(policy_id, version)
    )


@router.put(
    "/api/v1/policies/{policy_id}/versions/{version}/draft",
    response_model=PolicyDetailResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Update draft policy version",
    description="Replace editable draft policy version content.",
)
def update_draft_policy_version(
    policy_id: str,
    version: str,
    request: UpdateDraftPolicyVersionRequest,
    policy_service: Annotated[
        object,
        Depends(get_policy_administration_service),
    ],
) -> PolicyDetailResponse:
    return PolicyDetailResponse.from_domain(
        policy_service.update_draft_version(
            policy_id=policy_id,
            version=version,
            target_types=request.target_types,
            rules=_rules(request.rules),
            updated_by=request.updated_by,
            metadata=request.metadata,
        )
    )


@router.post(
    "/api/v1/policies/{policy_id}/versions/{version}/activate",
    response_model=PolicyDetailResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Activate policy version",
    description="Activate a draft version and deprecate the current active one.",
)
def activate_policy_version(
    policy_id: str,
    version: str,
    request: ActivatePolicyVersionRequest,
    policy_service: Annotated[
        object,
        Depends(get_policy_administration_service),
    ],
) -> PolicyDetailResponse:
    return PolicyDetailResponse.from_domain(
        policy_service.activate_version(
            policy_id=policy_id,
            version=version,
            activated_by=request.activated_by,
        )
    )


@router.post(
    "/api/v1/policies/{policy_id}/versions/{version}/archive",
    response_model=PolicyDetailResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Archive policy version",
    description="Archive a policy version so it cannot be activated later.",
)
def archive_policy_version(
    policy_id: str,
    version: str,
    request: ArchivePolicyVersionRequest,
    policy_service: Annotated[
        object,
        Depends(get_policy_administration_service),
    ],
) -> PolicyDetailResponse:
    return PolicyDetailResponse.from_domain(
        policy_service.archive_version(
            policy_id=policy_id,
            version=version,
            archived_by=request.archived_by,
        )
    )


@router.post(
    "/api/v1/policies/{policy_id}/versions/{version}/simulate",
    response_model=PolicySimulationResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Simulate policy version",
    description="Evaluate a policy version with backend-owned evaluator logic.",
)
def simulate_policy_version(
    policy_id: str,
    version: str,
    request: PolicySimulationRequest,
    policy_service: Annotated[
        object,
        Depends(get_policy_administration_service),
    ],
) -> PolicySimulationResponse:
    return PolicySimulationResponse.from_domain(
        policy_service.simulate_version(
            policy_id=policy_id,
            version=version,
            target_type=request.target_type,
            target_id=request.target_id,
            evidence=request.evidence,
            metadata=request.metadata,
        )
    )


def _rules(
    rules: list[CreatePolicyRuleRequest],
) -> tuple[PolicyRule, ...]:
    return tuple(
        build_policy_rule(
            rule_id=rule.rule_id,
            name=rule.name,
            conditions=[condition.model_dump() for condition in rule.conditions],
            effect=rule.effect,
            reason_template=rule.reason_template,
            priority=rule.priority,
            severity=rule.severity,
            metadata=rule.metadata,
        )
        for rule in rules
    )
