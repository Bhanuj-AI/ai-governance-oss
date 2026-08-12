from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from ai_governance.api.dependencies import get_prompt_registry_service
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models import (
    ErrorResponse,
    PromptDetailResponse,
    PromptCreateRequest,
    PromptObservationRequest,
    PromptResponse,
    PromptVersionCreateRequest,
)
from ai_governance.tenancy.domain import TenantContext

router = APIRouter(
    prefix="/api/v1/prompts",
    tags=["Prompts"],
)


@router.post(
    "/observations",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record observed prompt evidence",
    description=(
        "Record a prompt identity reported by a runtime or evaluation producer. "
        "This endpoint does not author prompts; content is optional and a hash is "
        "required when content is withheld."
    ),
)
def observe_prompt(
    request: PromptObservationRequest,
    prompt_registry_service: Annotated[object, Depends(get_prompt_registry_service)],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> PromptResponse:
    """Persist idempotent prompt execution evidence."""

    prompt = prompt_registry_service.observe_prompt(
        name=request.name,
        version=request.version,
        source_system=request.source_system,
        source_reference=request.source_reference,
        template=request.template,
        content_hash=request.content_hash,
        variables=request.variables,
        observed_by=tenant_context.actor_id,
        context=tenant_context,
    )
    return PromptResponse.from_domain(prompt)


@router.post(
    "",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a managed prompt",
    description="Create the first immutable managed prompt version in DRAFT status.",
)
def create_prompt(
    request: PromptCreateRequest,
    prompt_registry_service: Annotated[object, Depends(get_prompt_registry_service)],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> PromptResponse:
    prompt = prompt_registry_service.create_prompt(
        name=request.name,
        version=request.version,
        template=request.template,
        variables=request.variables,
        created_by=tenant_context.actor_id,
        context=tenant_context,
    )
    return PromptResponse.from_domain(prompt)


@router.post(
    "/{prompt_id}/versions",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a managed prompt version",
    description="Create an immutable DRAFT version from a managed prompt version.",
)
def create_prompt_version(
    prompt_id: str,
    request: PromptVersionCreateRequest,
    prompt_registry_service: Annotated[object, Depends(get_prompt_registry_service)],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> PromptResponse:
    prompt = prompt_registry_service.version_prompt(
        prompt_id=prompt_id,
        version=request.version,
        template=request.template,
        variables=request.variables,
        created_by=tenant_context.actor_id,
        context=tenant_context,
    )
    return PromptResponse.from_domain(prompt)


@router.get(
    "",
    response_model=list[PromptResponse],
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="List prompts",
    description="Return non-archived prompt version metadata.",
)
def list_prompts(
    prompt_registry_service: Annotated[
        object,
        Depends(get_prompt_registry_service),
    ],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> list[PromptResponse]:
    """
    Return visible prompt metadata.
    """

    return [
        PromptResponse.from_domain(prompt)
        for prompt in prompt_registry_service.list_visible_prompts(tenant_context)
    ]


@router.get(
    "/versions/{prompt_id}",
    response_model=PromptDetailResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Prompt version was not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="Get prompt version",
    description="Return one governed prompt version, including its template.",
)
def get_prompt_version(
    prompt_id: str,
    prompt_registry_service: Annotated[
        object,
        Depends(get_prompt_registry_service),
    ],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> PromptDetailResponse:
    """Return the complete registry representation for one prompt version."""

    return PromptDetailResponse.from_domain(
        prompt_registry_service.get_prompt(prompt_id, tenant_context)
    )


@router.get(
    "/{name}",
    response_model=list[PromptResponse],
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Prompt was not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="List prompt versions",
    description="Return non-archived versions for one logical prompt name.",
)
def list_prompt_versions(
    name: str,
    prompt_registry_service: Annotated[
        object,
        Depends(get_prompt_registry_service),
    ],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> list[PromptResponse]:
    """
    Return visible versions for one prompt name.
    """

    return [
        PromptResponse.from_domain(prompt)
        for prompt in prompt_registry_service.list_prompt_versions(name, tenant_context)
    ]
