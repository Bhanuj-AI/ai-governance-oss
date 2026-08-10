from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from ai_governance.api.dependencies import (
    get_evaluation_service,
    get_prompt_registry_service,
    get_provider_registry,
)
from ai_governance.api.models import ErrorResponse, HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="Health check",
    description="Return the liveness status of the AI Governance Control Plane REST API.",
)
def health() -> HealthResponse:
    """
    Return the liveness status of the REST process.
    """

    return HealthResponse(status="UP")


@router.get(
    "/ready",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Dependency creation failed.",
        },
    },
    summary="Readiness check",
    description="Verify the REST API can resolve its application dependencies.",
)
def ready(
    request: Request,
    evaluation_service: Annotated[
        object,
        Depends(get_evaluation_service),
    ],
    prompt_registry_service: Annotated[
        object,
        Depends(get_prompt_registry_service),
    ],
    provider_registry: Annotated[
        object,
        Depends(get_provider_registry),
    ],
) -> HealthResponse:
    """
    Return readiness after FastAPI dependency resolution succeeds.
    """

    for contributor in getattr(request.app.state, "plugin_health_contributors", ()):
        result = contributor.health()
        if str(result.get("status", "UP")).upper() not in {"UP", "HEALTHY"}:
            return HealthResponse(status="DOWN")
    return HealthResponse(status="UP")
