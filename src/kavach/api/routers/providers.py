from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from kavach.api.dependencies import get_provider_registry_service
from kavach.api.models import ErrorResponse, ProviderResponse

router = APIRouter(
    prefix="/api/v1/providers",
    tags=["Providers"],
)


@router.get(
    "",
    response_model=list[ProviderResponse],
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="List providers",
    description="Return descriptors for registered evaluation providers.",
)
def list_providers(
    provider_registry_service: Annotated[
        object,
        Depends(get_provider_registry_service),
    ],
) -> list[ProviderResponse]:
    """
    Return registered provider descriptors.
    """

    return [
        ProviderResponse.from_domain(provider)
        for provider in provider_registry_service.list_providers()
    ]


@router.get(
    "/{provider_name}",
    response_model=ProviderResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Provider was not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="Get provider",
    description="Return a single provider descriptor by provider name.",
)
def get_provider(
    provider_name: str,
    provider_registry_service: Annotated[
        object,
        Depends(get_provider_registry_service),
    ],
) -> ProviderResponse:
    """
    Return one provider descriptor.
    """

    return ProviderResponse.from_domain(
        provider_registry_service.get_provider(provider_name)
    )
