"""Local-development helpers for the Studio mentor."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ai_governance.api.demo_seed import seed_demo_data_for_app
from ai_governance.api.dependencies import ApiSettings, get_api_settings
from ai_governance.api.models import DemoSeedResponse, ErrorResponse

router = APIRouter(prefix="/api/v1/local/demo", tags=["Local demo"])

_LOCAL_ENVIRONMENTS = frozenset({"local", "dev", "development"})


@router.post(
    "/seed",
    response_model=DemoSeedResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Seed the complete local Studio demo",
    description=(
        "Idempotently seed the representative end-to-end workflow used by "
        "Studio's guided journeys. This endpoint is available only in local "
        "or development environments."
    ),
)
def seed_local_demo_data(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> DemoSeedResponse:
    if settings.environment not in _LOCAL_ENVIRONMENTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local demo data can only be seeded in local or development environments.",
        )

    return DemoSeedResponse(
        seeded=True,
        decision_ids=list(seed_demo_data_for_app(request.app)),
    )
