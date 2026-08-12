"""REST transport for tenant-owned model runtime connections."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ai_governance.api.dependencies.runtime_connections import get_runtime_connection_service
from ai_governance.api.dependencies.model_catalog_discovery import (
    get_model_catalog_discovery_service,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models.runtime_connection import (
    RuntimeConnectionCreateRequest,
    RuntimeConnectionProviderResponse,
    RuntimeConnectionResponse,
    RuntimeConnectionUpdateRequest,
    RuntimeConnectionValidationResponse,
    DiscoveredRuntimeModelResponse,
)
from ai_governance.domain.models import runtime_model_provider_display_name
from ai_governance.services.runtime_connection_service import (
    RuntimeConnectionNotFoundError,
    RuntimeConnectionProviderNotAllowedError,
    RuntimeConnectionProviderUnavailableError,
)
from ai_governance.services.model_catalog_discovery_service import (
    ModelCatalogDiscoveryError,
)
from ai_governance.tenancy.domain import TenantContext


router = APIRouter(prefix="/api/v1/runtime-connections", tags=["Runtime Connections"])


@router.get(
    "/providers",
    response_model=list[RuntimeConnectionProviderResponse],
    summary="List OSS runtime connection providers",
)
def list_runtime_connection_providers(
    service: Annotated[object, Depends(get_runtime_connection_service)],
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> list[RuntimeConnectionProviderResponse]:
    allowed = set(service.allowed_provider_keys(context))
    return [
        RuntimeConnectionProviderResponse(
            key=provider,
            display_name=runtime_model_provider_display_name(provider),
            allowed=provider in allowed,
        )
        for provider in service.supported_provider_keys()
    ]


@router.post(
    "/validate",
    response_model=RuntimeConnectionValidationResponse,
    summary="Test unsaved runtime connection configuration",
    description="Resolve secret references and validate OSS runtime adapter configuration without saving a connection.",
)
def validate_runtime_connection(
    request: RuntimeConnectionCreateRequest,
    service: Annotated[object, Depends(get_runtime_connection_service)],
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> RuntimeConnectionValidationResponse:
    try:
        service.validate_configuration(
            provider=request.provider,
            settings=request.settings,
            secret_refs=request.secret_refs,
            context=context,
        )
    except (
        RuntimeConnectionProviderUnavailableError,
        RuntimeConnectionProviderNotAllowedError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RuntimeConnectionValidationResponse(
        valid=True,
        provider=request.provider,
        message="Configuration and secret references resolved successfully.",
    )


@router.get("", response_model=list[RuntimeConnectionResponse], summary="List runtime connections")
def list_runtime_connections(
    service: Annotated[object, Depends(get_runtime_connection_service)],
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> list[RuntimeConnectionResponse]:
    return [RuntimeConnectionResponse.from_domain(item) for item in service.list(context)]


@router.get(
    "/{runtime_connection_id}/models",
    response_model=list[DiscoveredRuntimeModelResponse],
    summary="Discover provider-visible model IDs",
    description=(
        "Use the selected runtime connection to list provider-visible model IDs. "
        "Credentials remain secret references and are never returned."
    ),
)
def discover_runtime_connection_models(
    runtime_connection_id: str,
    service: Annotated[object, Depends(get_model_catalog_discovery_service)],
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> list[DiscoveredRuntimeModelResponse]:
    try:
        return [
            DiscoveredRuntimeModelResponse(provider_model_id=item.provider_model_id)
            for item in service.discover(runtime_connection_id, context)
        ]
    except RuntimeConnectionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime connection was not found.") from exc
    except ModelCatalogDiscoveryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "",
    response_model=RuntimeConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create runtime connection",
    description="Create a tenant-owned model runtime connection. Credentials are secret references only.",
)
def create_runtime_connection(
    request: RuntimeConnectionCreateRequest,
    service: Annotated[object, Depends(get_runtime_connection_service)],
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> RuntimeConnectionResponse:
    try:
        connection = service.create(
            display_name=request.display_name,
            provider=request.provider,
            settings=request.settings,
            secret_refs=request.secret_refs,
            enabled=request.enabled,
            project_id=context.project_id if request.scope == "PROJECT" else None,
            context=context,
        )
    except (
        RuntimeConnectionProviderUnavailableError,
        RuntimeConnectionProviderNotAllowedError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RuntimeConnectionResponse.from_domain(connection)


@router.patch("/{runtime_connection_id}", response_model=RuntimeConnectionResponse, summary="Update runtime connection")
def update_runtime_connection(
    runtime_connection_id: str,
    request: RuntimeConnectionUpdateRequest,
    service: Annotated[object, Depends(get_runtime_connection_service)],
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> RuntimeConnectionResponse:
    try:
        connection = service.update(
            runtime_connection_id,
            display_name=request.display_name,
            settings=request.settings,
            secret_refs=request.secret_refs,
            enabled=request.enabled,
            context=context,
        )
    except RuntimeConnectionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime connection was not found.") from exc
    except (
        RuntimeConnectionProviderUnavailableError,
        RuntimeConnectionProviderNotAllowedError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RuntimeConnectionResponse.from_domain(connection)


@router.post(
    "/{runtime_connection_id}/test",
    response_model=RuntimeConnectionResponse,
    summary="Test saved runtime connection",
    description="Record the result of local configuration and secret-reference validation without returning secret values.",
)
def test_runtime_connection(
    runtime_connection_id: str,
    service: Annotated[object, Depends(get_runtime_connection_service)],
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> RuntimeConnectionResponse:
    try:
        connection = service.test(runtime_connection_id, context)
    except RuntimeConnectionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime connection was not found.") from exc
    return RuntimeConnectionResponse.from_domain(connection)
