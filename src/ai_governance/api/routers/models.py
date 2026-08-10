from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from ai_governance.api.dependencies import get_model_registry_service
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models import ErrorResponse, ModelObservationRequest, ModelResponse
from ai_governance.tenancy.domain import TenantContext

router = APIRouter(
    prefix="/api/v1/models",
    tags=["Models"],
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
    )
    return ModelResponse.from_domain(model)


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
) -> list[ModelResponse]:
    """
    Return model registry metadata.
    """

    return [
        ModelResponse.from_domain(model)
        for model in model_registry_service.list_models()
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
) -> ModelResponse:
    """
    Return model metadata by ID.
    """

    return ModelResponse.from_domain(model_registry_service.get_model(model_id))
