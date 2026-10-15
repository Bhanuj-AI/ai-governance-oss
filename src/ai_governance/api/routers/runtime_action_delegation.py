"""Issuer-only public lifecycle for immutable runtime action delegations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from ai_governance.api.dependencies.runtime_action_delegation import (
    get_runtime_action_delegation_service,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.mappers.runtime_action_delegation_mapper import (
    RuntimeActionDelegationApiMapper,
)
from ai_governance.api.models.error import ErrorBody, ErrorResponse
from ai_governance.api.models.runtime_action_delegation import (
    RuntimeActionDelegationRegistrationRequest,
    RuntimeActionDelegationResponse,
    RuntimeActionDelegationRevokeRequest,
)
from ai_governance.services.runtime_action_delegation_service import (
    RuntimeActionDelegationConflictError,
    RuntimeActionDelegationDeniedError,
    RuntimeActionDelegationNotFoundError,
)

router = APIRouter(
    prefix="/api/v1/runtime-action-delegations", tags=["Runtime action delegations"]
)


@router.post(
    "",
    response_model=RuntimeActionDelegationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def register_runtime_action_delegation(
    request: RuntimeActionDelegationRegistrationRequest,
    service: Annotated[object, Depends(get_runtime_action_delegation_service)],
    context=Depends(get_compatible_tenant_context),
) -> RuntimeActionDelegationResponse:
    try:
        delegation = service.register(request.to_service(), context)
    except RuntimeActionDelegationNotFoundError as exc:
        return _error(
            status.HTTP_404_NOT_FOUND,
            "RUNTIME_ACTION_DELEGATION_EXECUTION_NOT_FOUND",
            str(exc),
        )
    except RuntimeActionDelegationDeniedError as exc:
        return _error(
            status.HTTP_403_FORBIDDEN, "RUNTIME_ACTION_DELEGATION_DENIED", str(exc)
        )
    except RuntimeActionDelegationConflictError as exc:
        return _error(
            status.HTTP_409_CONFLICT, "RUNTIME_ACTION_DELEGATION_CONFLICT", str(exc)
        )
    return RuntimeActionDelegationApiMapper.to_response(delegation)


@router.post(
    "/{delegation_id}/revoke",
    response_model=RuntimeActionDelegationResponse,
    responses={404: {"model": ErrorResponse}},
)
def revoke_runtime_action_delegation(
    delegation_id: str,
    request: RuntimeActionDelegationRevokeRequest,
    service: Annotated[object, Depends(get_runtime_action_delegation_service)],
    context=Depends(get_compatible_tenant_context),
) -> RuntimeActionDelegationResponse:
    try:
        delegation = service.revoke(
            delegation_id,
            revocation_reference=request.revocation_reference,
            context=context,
        )
    except RuntimeActionDelegationNotFoundError as exc:
        return _error(
            status.HTTP_404_NOT_FOUND, "RUNTIME_ACTION_DELEGATION_NOT_FOUND", str(exc)
        )
    return RuntimeActionDelegationApiMapper.to_response(delegation)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": ErrorBody(code=code, message=message).model_dump()},
    )
