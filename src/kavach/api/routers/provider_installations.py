"""REST transport for tenant-managed evaluation provider installations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from kavach.api.dependencies.provider_installations import get_provider_installation_service
from kavach.api.dependencies.tenancy import get_compatible_tenant_context
from kavach.api.models import (
    ErrorResponse,
    ProviderInstallationCreateRequest,
    ProviderInstallationResponse,
    ProviderInstallationValidationResponse,
    ProviderInstallationUpdateRequest,
)
from kavach.services.provider_installation_service import (
    ProviderInstallationNotFoundError,
    ProviderInstallationTypeUnavailableError,
)


router = APIRouter(prefix="/api/v1/provider-installations", tags=["Provider Installations"])


@router.post(
    "/validate",
    response_model=ProviderInstallationValidationResponse,
    summary="Validate provider installation configuration",
    description="Resolve secret references and initialize the selected provider without saving an installation.",
)
def validate_provider_installation(
    request: ProviderInstallationCreateRequest,
    service: Annotated[object, Depends(get_provider_installation_service)],
    context=Depends(get_compatible_tenant_context),
) -> ProviderInstallationValidationResponse:
    try:
        service.validate_configuration(
            provider_type=request.provider_type,
            settings=request.settings,
            secret_refs=request.secret_refs,
            context=context,
        )
    except (ProviderInstallationTypeUnavailableError, ValueError) as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProviderInstallationValidationResponse(
        valid=True,
        provider_type=request.provider_type,
        message="Secret references resolved and provider initialization succeeded.",
    )


@router.get("", response_model=list[ProviderInstallationResponse], summary="List provider installations")
def list_provider_installations(
    service: Annotated[object, Depends(get_provider_installation_service)],
    context=Depends(get_compatible_tenant_context),
) -> list[ProviderInstallationResponse]:
    return [ProviderInstallationResponse.from_domain(item) for item in service.list(context)]


@router.post(
    "",
    response_model=ProviderInstallationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse}},
    summary="Create provider installation",
    description="Create one tenant-scoped configuration for a provider type shipped by this deployment.",
)
def create_provider_installation(
    request: ProviderInstallationCreateRequest,
    service: Annotated[object, Depends(get_provider_installation_service)],
    context=Depends(get_compatible_tenant_context),
) -> ProviderInstallationResponse:
    try:
        item = service.create(
            provider_type=request.provider_type,
            display_name=request.display_name,
            settings=request.settings,
            secret_refs=request.secret_refs,
            enabled=request.enabled,
            project_id=context.project_id if request.scope == "PROJECT" else None,
            context=context,
        )
    except (ProviderInstallationTypeUnavailableError, ValueError) as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProviderInstallationResponse.from_domain(item)


@router.patch(
    "/{installation_id}",
    response_model=ProviderInstallationResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
    summary="Update provider installation",
)
def update_provider_installation(
    installation_id: str,
    request: ProviderInstallationUpdateRequest,
    service: Annotated[object, Depends(get_provider_installation_service)],
    context=Depends(get_compatible_tenant_context),
) -> ProviderInstallationResponse:
    try:
        item = service.update(
            installation_id,
            display_name=request.display_name,
            settings=request.settings,
            secret_refs=request.secret_refs,
            enabled=request.enabled,
            context=context,
        )
    except ProviderInstallationNotFoundError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProviderInstallationResponse.from_domain(item)
