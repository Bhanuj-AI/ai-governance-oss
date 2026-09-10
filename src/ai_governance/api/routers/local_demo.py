"""Local-development helpers for the Studio mentor."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ai_governance.api.demo_agent_runtime import (
    is_agent_runtime_demo_seeded,
    seed_agent_runtime_data,
)
from ai_governance.api.demo_seed import seed_demo_data_for_app
from ai_governance.api.dependencies import ApiSettings, get_api_settings
from ai_governance.api.models import (
    AgentRuntimeDemoStatusResponse,
    DemoSeedResponse,
    ErrorResponse,
)

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


@router.get(
    "/agent-runtime/status",
    response_model=AgentRuntimeDemoStatusResponse,
    responses={status.HTTP_403_FORBIDDEN: {"model": ErrorResponse}},
    summary="Read local Agent Runtime demo availability",
)
def get_agent_runtime_demo_status(
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> AgentRuntimeDemoStatusResponse:
    """Report whether the complete runtime sample is already present."""
    if settings.environment not in _LOCAL_ENVIRONMENTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent runtime demo data is only available in local or development environments.",
        )

    from ai_governance.api.dependencies import (
        get_agent_execution_service,
        get_causal_audit_repository,
        get_runtime_finding_repository,
    )

    exec_service = get_agent_execution_service()
    return AgentRuntimeDemoStatusResponse(
        seeded=is_agent_runtime_demo_seeded(
            execution_repo=exec_service._execution_repo,
            finding_repo=get_runtime_finding_repository(),
            causal_audit_repo=get_causal_audit_repository(),
        )
    )


@router.post(
    "/agent-runtime",
    response_model=DemoSeedResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Seed agent runtime demo data (executions + findings)",
    description=(
        "Idempotently seed realistic agent executions and deterministic runtime "
        "findings for the Agent Runtime page. Covers all statuses, severities, "
        "and detector types. Available only in local or development environments."
    ),
)
def seed_agent_runtime_demo(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> DemoSeedResponse:
    if settings.environment not in _LOCAL_ENVIRONMENTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent runtime demo data can only be seeded in local or development environments.",
        )

    from ai_governance.api.dependencies import (
        get_agent_execution_service,
        get_causal_audit_repository,
        get_runtime_finding_repository,
    )

    exec_service = get_agent_execution_service()
    finding_repo = get_runtime_finding_repository()

    result = seed_agent_runtime_data(
        execution_repo=exec_service._execution_repo,
        event_repo=exec_service._event_repo,
        finding_repo=finding_repo,
        causal_audit_repo=get_causal_audit_repository(),
    )

    return DemoSeedResponse(
        seeded=True,
        decision_ids=result["execution_ids"]
        + result["finding_ids"]
        + result["causal_audit_ids"],
    )
