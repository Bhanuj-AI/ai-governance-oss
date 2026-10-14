"""Public endpoint for external runtime action authorization."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from ai_governance.api.dependencies.runtime_action_authorization import (
    get_runtime_action_authorization_service,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.mappers.runtime_action_authorization_mapper import (
    RuntimeActionAuthorizationApiMapper,
)
from ai_governance.api.models.error import ErrorBody, ErrorResponse
from ai_governance.api.models.runtime_action_authorization import (
    RuntimeActionAuthorizationRequestBody,
    RuntimeActionAuthorizationResponse,
)
from ai_governance.services.runtime_action_authorization_service import (
    RuntimeActionAuthorizationConflictError,
    RuntimeActionAuthorizationNotFoundError,
    RuntimeActionAuthorizationPersistenceError,
)

router = APIRouter(
    prefix="/api/v1/runtime-action-authorizations",
    tags=["Runtime action authorization"],
)


@router.post(
    "/authorize",
    response_model=RuntimeActionAuthorizationResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Authorize one external runtime action",
    description=(
        "Evaluate and persist an authoritative ALLOW or DENY for exactly one "
        "registered operation. This endpoint never executes the operation; "
        "external runtimes must fail closed unless the returned ALLOW is still "
        "valid for the same execution, actor, action, and resource."
    ),
)
def authorize_runtime_action(
    request: RuntimeActionAuthorizationRequestBody,
    service: Annotated[
        object,
        Depends(get_runtime_action_authorization_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> RuntimeActionAuthorizationResponse:
    try:
        decision = service.authorize(request.to_domain(), context)
    except RuntimeActionAuthorizationNotFoundError as exc:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "RUNTIME_ACTION_EXECUTION_NOT_FOUND",
            str(exc),
        )
    except RuntimeActionAuthorizationConflictError as exc:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "RUNTIME_ACTION_AUTHORIZATION_CONFLICT",
            str(exc),
        )
    except RuntimeActionAuthorizationPersistenceError as exc:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "RUNTIME_ACTION_AUTHORIZATION_UNAVAILABLE",
            str(exc),
        )
    return RuntimeActionAuthorizationApiMapper.to_response(decision)


def _error_response(
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": ErrorBody(code=code, message=message).model_dump()},
    )
