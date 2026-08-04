from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status as http_status

from kavach.api.dependencies import get_dashboard_read_service
from kavach.api.mappers.dashboard_mapper import DashboardApiMapper
from kavach.api.models import DashboardSummaryResponse, ErrorResponse

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)


@router.get(
    "",
    response_model=DashboardSummaryResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
        },
    },
    summary="Get dashboard summary",
    description="Return the Studio home dashboard read model.",
)
def get_dashboard_summary(
    dashboard_read_service: Annotated[
        object,
        Depends(get_dashboard_read_service),
    ],
) -> DashboardSummaryResponse:
    """
    Return the dashboard summary without requiring frontend request fan-out.
    """
    return DashboardApiMapper.to_response(dashboard_read_service.get_summary())
