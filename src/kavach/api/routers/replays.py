from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from kavach.api.dependencies import get_replay_application_service, get_replay_audit_service
from kavach.api.dependencies.tenancy import get_compatible_tenant_context
from kavach.api.mappers.replay_mapper import ReplayApiMapper
from kavach.api.models import (
    ErrorResponse,
    ReplayArchiveRequest,
    ReplayAuditRecordResponse,
    ReplayCreateRequest,
    ReplayEvaluateRequest,
    ReplayMutationDryRunResponse,
    ReplayMutationRequest,
    ReplayResponse,
    ReplaySubmitResponse,
    ReplayResultResponse,
)
from kavach.domain.replay import ReplayStatus
from kavach.services.replay_application_service import ReplayListFilters


router = APIRouter(prefix="/api/v1/replays", tags=["Replays"])


@router.post(
    "",
    response_model=ReplayResponse | dict[str, Any],
    status_code=status.HTTP_201_CREATED,
)
def create_replay(
    request: ReplayCreateRequest,
    service: Annotated[object, Depends(get_replay_application_service)],
    context=Depends(get_compatible_tenant_context),
) -> ReplayResponse | dict[str, Any]:
    if request.dry_run:
        configuration = service.dry_run(
            source_execution_id=request.source_execution_id,
            context=context,
            mode=request.mode,
            configuration_source=request.configuration_source,
        )
        return {
            "dry_run": True,
            "replayable": True,
            "configuration": ReplayApiMapper.to_configuration_response(
                configuration
            ).model_dump(mode="json"),
        }
    replay = service.create(
        source_execution_id=request.source_execution_id,
        context=context,
        idempotency_key=request.idempotency_key,
        mode=request.mode,
        configuration_source=request.configuration_source,
        metadata={
            **request.metadata,
            **({"reason": request.reason} if request.reason else {}),
        },
    )
    return ReplayApiMapper.to_response(replay)


@router.get("", response_model=list[ReplayResponse])
def list_replays(
    service: Annotated[object, Depends(get_replay_application_service)],
    context=Depends(get_compatible_tenant_context),
    status_filter: ReplayStatus | None = Query(None, alias="status"),
    source_execution_id: str | None = None,
    requested_by: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: int = Query(100, ge=1, le=200),
) -> list[ReplayResponse]:
    filters = ReplayListFilters(
        status=status_filter,
        source_execution_id=source_execution_id,
        requested_by=requested_by,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
    )
    return [
        ReplayApiMapper.to_response(replay) for replay in service.list(context, filters)
    ]


@router.get(
    "/{replay_id}/audit",
    response_model=list[ReplayAuditRecordResponse],
    responses={404: {"model": ErrorResponse}},
    summary="List replay audit timeline",
    description=(
        "Return the replay-scoped timeline assembled from the durable Replay "
        "aggregate and its execution/evaluation jobs."
    ),
)
def list_replay_audit_records(
    replay_id: str,
    service: Annotated[object, Depends(get_replay_audit_service)],
    context=Depends(get_compatible_tenant_context),
) -> list[ReplayAuditRecordResponse]:
    return [
        ReplayApiMapper.to_audit_record_response(record)
        for record in service.list_records(replay_id, context)
    ]


@router.get(
    "/{replay_id}",
    response_model=ReplayResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_replay(
    replay_id: str,
    service: Annotated[object, Depends(get_replay_application_service)],
    context=Depends(get_compatible_tenant_context),
) -> ReplayResponse:
    return ReplayApiMapper.to_response(service.get(replay_id, context))


@router.post("/{replay_id}/archive", response_model=ReplayResponse)
def archive_replay(
    replay_id: str,
    request: ReplayArchiveRequest,
    service: Annotated[object, Depends(get_replay_application_service)],
    context=Depends(get_compatible_tenant_context),
) -> ReplayResponse:
    replay = service.archive(replay_id, context)
    return ReplayApiMapper.to_response(replay)


@router.post(
    "/{replay_id}/submit",
    response_model=ReplaySubmitResponse | ReplayMutationDryRunResponse,
)
def submit_replay(
    replay_id: str,
    request: ReplayMutationRequest,
    service: Annotated[object, Depends(get_replay_application_service)],
    context=Depends(get_compatible_tenant_context),
) -> ReplaySubmitResponse | ReplayMutationDryRunResponse:
    if request.dry_run:
        replay = service.validate_submission(replay_id, context)
        return ReplayMutationDryRunResponse(
            operation="SUBMIT_REPLAY_EXECUTION",
            replay=ReplayApiMapper.to_response(replay),
        )
    replay = service.submit(replay_id, context)
    return ReplaySubmitResponse(
        replay=ReplayApiMapper.to_response(replay),
        job_id=replay.job_id or "",
        job_status="QUEUED" if replay.status.value == "QUEUED" else replay.status.value,
    )


@router.post(
    "/{replay_id}/cancel",
    response_model=ReplayResponse | ReplayMutationDryRunResponse,
)
def cancel_replay(
    replay_id: str,
    request: ReplayMutationRequest,
    service: Annotated[object, Depends(get_replay_application_service)],
    context=Depends(get_compatible_tenant_context),
) -> ReplayResponse | ReplayMutationDryRunResponse:
    if request.dry_run:
        replay = service.validate_cancellation(replay_id, context)
        return ReplayMutationDryRunResponse(
            operation="CANCEL_REPLAY_EXECUTION",
            replay=ReplayApiMapper.to_response(replay),
        )
    return ReplayApiMapper.to_response(service.cancel(replay_id, context))


@router.post(
    "/{replay_id}/evaluate",
    response_model=ReplayResponse | ReplayMutationDryRunResponse,
)
def evaluate_replay(
    replay_id: str,
    request: ReplayEvaluateRequest,
    service: Annotated[object, Depends(get_replay_application_service)],
    context=Depends(get_compatible_tenant_context),
) -> ReplayResponse | ReplayMutationDryRunResponse:
    if request.dry_run:
        replay = service.validate_evaluation(
            replay_id, context, evaluation_provider=request.evaluation_provider,
            provider_installation_id=request.provider_installation_id,
            baseline_strategy=request.baseline_strategy,
            baseline_evaluation_id=request.baseline_evaluation_id,
        )
        return ReplayMutationDryRunResponse(
            operation="SUBMIT_REPLAY_EVALUATION", replay=ReplayApiMapper.to_response(replay)
        )
    replay = service.evaluate(
        replay_id, context, evaluation_provider=request.evaluation_provider,
        provider_installation_id=request.provider_installation_id,
        baseline_strategy=request.baseline_strategy,
        baseline_evaluation_id=request.baseline_evaluation_id,
    )
    return ReplayApiMapper.to_response(replay)


@router.get("/{replay_id}/result", response_model=ReplayResultResponse)
def get_replay_result(
    replay_id: str,
    service: Annotated[object, Depends(get_replay_application_service)],
    context=Depends(get_compatible_tenant_context),
) -> ReplayResultResponse:
    return ReplayApiMapper.to_result_response(service.get_result(replay_id, context))
