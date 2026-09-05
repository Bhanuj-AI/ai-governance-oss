from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from ai_governance.api.dependencies import get_dashboard_read_service
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.mappers.dashboard_mapper import DashboardApiMapper
from ai_governance.api.models import DashboardSummaryResponse, ErrorResponse
from ai_governance.tenancy.domain import TenantContext

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
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> DashboardSummaryResponse:
    """
    Return the dashboard summary without requiring frontend request fan-out.
    """
    return DashboardApiMapper.to_response(dashboard_read_service.get_summary(context))
