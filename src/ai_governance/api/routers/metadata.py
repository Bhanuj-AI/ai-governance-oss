from __future__ import annotations

from fastapi import APIRouter, Depends, status

from ai_governance import __version__
from ai_governance.api.models import ErrorResponse, MetadataResponse
from ai_governance.api.dependencies.settings_control import get_configuration_service
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.settings_control.operational import setting_context

router = APIRouter(
    prefix="/api/v1",
    tags=["Metadata"],
)


@router.get(
    "",
    response_model=MetadataResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="API metadata",
    description="Return product and REST API version metadata.",
)
def metadata(
    context=Depends(get_compatible_tenant_context),
    configuration_service=Depends(get_configuration_service),
) -> MetadataResponse:
    """
    Return stable metadata for the versioned REST API.
    """

    return MetadataResponse(
        name=str(
            configuration_service.get("general.instance_name", setting_context(context))
        ),
        version=__version__,
        api_version="v1",
        timezone=str(
            configuration_service.get("general.timezone", setting_context(context))
        ),
    )
