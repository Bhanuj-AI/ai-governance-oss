from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ai_governance.api.dependencies import get_model_registry_service
from ai_governance.api.dependencies.authorization import enforce_permission
from ai_governance.api.dependencies.runtime_connections import get_runtime_connection_service
from ai_governance.api.dependencies.settings_control import get_configuration_service
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models import (
    ErrorResponse,
    ModelCapabilityResolveRequest,
    ModelObservationRequest,
    ModelRegisterRequest,
    ModelRuntimeCapabilitiesResponse,
    ModelResponse,
    ModelVersionCreateRequest,
    RuntimeModelProviderResponse,
)
from ai_governance.domain.models import runtime_model_provider_display_name
from ai_governance.services.models import (
    ModelLifecycleError,
    ModelNotFoundError,
    ModelProviderNotAllowedError,
    ModelRuntimeParameterError,
    ModelVersionConflictError,
    resolve_runtime_capabilities,
)
from ai_governance.settings_control import ConfigurationService
from ai_governance.settings_control.domain import SettingContext
from ai_governance.tenancy.domain import TenantContext
from ai_governance.tenancy.permissions import Permission

router = APIRouter(
    prefix="/api/v1/models",
    tags=["Models"],
)


@router.get(
    "/runtime-providers",
    response_model=list[RuntimeModelProviderResponse],
    status_code=status.HTTP_200_OK,
    summary="List managed model runtime providers",
    description=(
        "Return OSS providers with runtime-connection and candidate-execution "
        "adapters, together with their tenant policy status."
    ),
)
def list_runtime_providers(
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
    configuration_service: Annotated[
        ConfigurationService, Depends(get_configuration_service)
    ],
    runtime_connection_service: Annotated[object, Depends(get_runtime_connection_service)],
) -> list[RuntimeModelProviderResponse]:
    allowed = set(
        configuration_service.get(
            "model_registry.allowed_runtime_providers",
            SettingContext(
                tenant_context.organization_id,
                tenant_context.project_id,
            ),
        )
    )
    return [
        RuntimeModelProviderResponse(
            key=provider,
            display_name=runtime_model_provider_display_name(provider),
            allowed=provider in allowed,
        )
        for provider in runtime_connection_service.supported_provider_keys()
    ]


@router.post(
    "/runtime-capabilities/resolve",
    response_model=ModelRuntimeCapabilitiesResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve a managed model runtime capability profile",
    description=(
        "Return the provider-neutral, immutable capability profile that will be "
        "stored when this managed model version is registered."
    ),
)
def resolve_model_runtime_capabilities(
    request: ModelCapabilityResolveRequest,
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> ModelRuntimeCapabilitiesResponse:
    # Tenant context is resolved before returning a policy-relevant profile.
    del tenant_context
    return ModelRuntimeCapabilitiesResponse.from_domain(
        resolve_runtime_capabilities(
            request.provider, request.provider_model_id or request.model_name
        )
    )


@router.post(
    "/observations",
    response_model=ModelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record observed model runtime evidence",
    description=(
        "Record a model identity and runtime configuration reported by an "
        "execution/evaluation producer. AI Governance Control Plane does not configure the runtime."
    ),
)
def observe_model(
    request: ModelObservationRequest,
    model_registry_service: Annotated[object, Depends(get_model_registry_service)],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> ModelResponse:
    """Persist idempotent model execution evidence."""

    model = model_registry_service.observe_model(
        provider=request.provider,
        model_name=request.model_name,
        version=request.version,
        source_system=request.source_system,
        source_reference=request.source_reference,
        parameters=request.parameters,
        context_window=request.context_window,
        observed_by=tenant_context.actor_id,
        cost=request.cost,
        latency=request.latency,
        context=tenant_context,
    )
    return ModelResponse.from_domain(model)


@router.post(
    "",
    response_model=ModelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a managed model",
    description="Register an immutable managed model/runtime configuration in DRAFT status.",
)
def register_model(
    request: ModelRegisterRequest,
    model_registry_service: Annotated[object, Depends(get_model_registry_service)],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> ModelResponse:
    try:
        model = model_registry_service.register_model(
            provider=request.provider,
            model_name=request.model_name,
            provider_model_id=request.provider_model_id,
            version=request.version,
            parameters=request.parameters,
            context_window=request.context_window,
            creator=tenant_context.actor_id,
            cost=request.cost,
            latency=request.latency,
            context=tenant_context,
        )
    except (ModelProviderNotAllowedError, ModelRuntimeParameterError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ModelResponse.from_domain(model)


@router.post(
    "/{model_id}/versions",
    response_model=ModelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a managed model version",
    description="Create an immutable DRAFT version from a managed model version.",
)
def create_model_version(
    model_id: str,
    request: ModelVersionCreateRequest,
    model_registry_service: Annotated[object, Depends(get_model_registry_service)],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> ModelResponse:
    try:
        model = model_registry_service.create_model_version(
            model_id=model_id,
            version=request.version,
            provider_model_id=request.provider_model_id,
            parameters=request.parameters,
            cost=request.cost,
            latency=request.latency,
            context_window=request.context_window,
            creator=tenant_context.actor_id,
            context=tenant_context,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' was not found.",
        ) from exc
    except (ModelLifecycleError, ModelVersionConflictError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ModelRuntimeParameterError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ModelResponse.from_domain(model)


@router.post(
    "/{model_id}/activate",
    response_model=ModelResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(enforce_permission(Permission.ASSET_MANAGE))],
    summary="Activate a managed model version",
    description=(
        "Activate a managed model version and deprecate any other active "
        "version of the same logical model in the selected tenant scope."
    ),
)
def activate_model(
    model_id: str,
    model_registry_service: Annotated[object, Depends(get_model_registry_service)],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> ModelResponse:
    return ModelResponse.from_domain(
        _transition_model(
            model_registry_service.activate_model_version,
            model_id,
            tenant_context,
        )
    )


@router.post(
    "/{model_id}/deprecate",
    response_model=ModelResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(enforce_permission(Permission.ASSET_MANAGE))],
    summary="Deprecate a managed model version",
    description="Mark a managed model version as deprecated while preserving history.",
)
def deprecate_model(
    model_id: str,
    model_registry_service: Annotated[object, Depends(get_model_registry_service)],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> ModelResponse:
    return ModelResponse.from_domain(
        _transition_model(
            model_registry_service.deprecate_model_version,
            model_id,
            tenant_context,
        )
    )


@router.post(
    "/{model_id}/archive",
    response_model=ModelResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(enforce_permission(Permission.ASSET_MANAGE))],
    summary="Archive a managed model version",
    description="Archive a managed model version so it is no longer deployable.",
)
def archive_model(
    model_id: str,
    model_registry_service: Annotated[object, Depends(get_model_registry_service)],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> ModelResponse:
    return ModelResponse.from_domain(
        _transition_model(
            model_registry_service.archive_model,
            model_id,
            tenant_context,
        )
    )


def _transition_model(operation, model_id: str, context: TenantContext):
    try:
        return operation(model_id, context)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' was not found.",
        ) from exc
    except ModelLifecycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[ModelResponse],
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="List models",
    description="Return metadata for registered model versions.",
)
def list_models(
    model_registry_service: Annotated[
        object,
        Depends(get_model_registry_service),
    ],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> list[ModelResponse]:
    """
    Return model registry metadata.
    """

    return [
        ModelResponse.from_domain(model)
        for model in model_registry_service.list_models(tenant_context)
    ]


@router.get(
    "/{model_id}",
    response_model=ModelResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Model was not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="Get model",
    description="Return metadata for a registered model version by ID.",
)
def get_model(
    model_id: str,
    model_registry_service: Annotated[
        object,
        Depends(get_model_registry_service),
    ],
    tenant_context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> ModelResponse:
    """
    Return model metadata by ID.
    """

    return ModelResponse.from_domain(model_registry_service.get_model(model_id, tenant_context))
