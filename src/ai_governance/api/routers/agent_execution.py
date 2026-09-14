"""REST API for agent execution trace ingestion and reads.

External runtimes POST to /api/v1/agent-executions to start executions
and ingest events. Platform consumers GET execution details and timelines.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models.agent_execution import (
    AgentExecutionAgentListResponse,
    AgentExecutionAgentSummaryResponse,
    AgentExecutionCompletedResponse,
    AgentExecutionDetailResponse,
    AgentExecutionEventIngestedResponse,
    AgentExecutionEventRequest,
    AgentExecutionEventResponse,
    AgentExecutionListResponse,
    AgentExecutionResponse,
    AgentExecutionStartedResponse,
    AgentExecutionStartRequest,
    AgentExecutionSummaryResponse,
)
from ai_governance.domain.agent_execution import (
    AgentExecutionStatus,
    EventType,
    WorkflowStep,
    WorkflowStepLifecycle,
)
from ai_governance.domain.agent_execution.agent_execution_event import (
    ActorType as AgentExecutionActorType,
)
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.tenancy.domain import TenantContext

router = APIRouter(prefix="/api/v1/agent-executions", tags=["Agent executions"])


# -- Execution start ------------------------------------------------------------


@router.post(
    "",
    response_model=AgentExecutionStartedResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_agent_execution(
    body: Annotated[AgentExecutionStartRequest, ...],
    service: Annotated[AgentExecutionService, Depends(get_agent_execution_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> AgentExecutionStartedResponse:
    """Ingest an EXECUTION_STARTED event from an external runtime.

    Duplicate delivery with the same (tenant, runtime_provider,
    external_execution_id) is idempotent and returns the existing record.
    """
    try:
        execution = service.ingest_start(
            agent_id=body.agent_id,
            agent_name=body.agent_name,
            agent_version=body.agent_version,
            external_execution_id=body.external_execution_id,
            runtime_provider=body.runtime_provider,
            correlation_id=body.correlation_id,
            parent_execution_id=body.parent_execution_id,
            metadata=body.metadata,
            context=context,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return AgentExecutionStartedResponse(execution=_execution_to_response(execution))


# -- Event ingestion -----------------------------------------------------------


@router.post(
    "/{execution_id}/events",
    response_model=AgentExecutionEventIngestedResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_event(
    execution_id: str,
    body: Annotated[AgentExecutionEventRequest, ...],
    service: Annotated[AgentExecutionService, Depends(get_agent_execution_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> AgentExecutionEventIngestedResponse:
    """Ingest a runtime event, including provider-neutral WORKFLOW_STEP evidence."""
    try:
        event_type = EventType(body.event_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported event type '{body.event_type}'. Supported: {[e.value for e in EventType]}",
        ) from exc

    try:
        actor_type = None
        if body.actor_type is not None:
            try:
                actor_type = AgentExecutionActorType(body.actor_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported actor type '{body.actor_type}'.",
                ) from None

        workflow_step = None
        if event_type is EventType.WORKFLOW_STEP:
            # The request model has already required these fields.  Construct
            # the named domain value object at the transport boundary so the
            # service never receives an untyped provider payload.
            workflow_step = WorkflowStep(
                step_id=body.step_id or "",
                step_name=body.step_name or "",
                lifecycle=WorkflowStepLifecycle(body.lifecycle or ""),
                parent_step_id=body.parent_step_id,
                source_kind=body.source_kind,
            )

        event = service.ingest_event(
            execution_id=execution_id,
            event_type=event_type,
            attributes=body.attributes,
            context=context,
            idempotency_key=body.idempotency_key,
            correlation_id=body.correlation_id,
            causation_id=body.causation_id,
            actor_id=body.actor_id,
            actor_type=actor_type,
            workflow_step=workflow_step,
            resource_references=body.resource_references,
            evidence_references=body.evidence_references,
            occurred_at=body.occurred_at,
        )
    except HTTPException:
        raise
    except Exception as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        if "conflict" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return AgentExecutionEventIngestedResponse(event=_event_to_response(event))


# -- Execution completion ------------------------------------------------------


@router.post(
    "/{execution_id}/complete",
    response_model=AgentExecutionCompletedResponse,
)
def complete_agent_execution(
    execution_id: str,
    body: Annotated[dict[str, Any], ...],
    service: Annotated[AgentExecutionService, Depends(get_agent_execution_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> AgentExecutionCompletedResponse:
    """Mark an execution as terminal (SUCCEEDED, FAILED, CANCELLED)."""
    status_value = body.get("status")
    if status_value not in ("SUCCEEDED", "FAILED", "CANCELLED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be SUCCEEDED, FAILED, or CANCELLED.",
        )

    try:
        execution = service.mark_completed(
            execution_id,
            AgentExecutionStatus(status_value),
            context,
        )
    except HTTPException:
        raise
    except Exception as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return AgentExecutionCompletedResponse(execution=_execution_to_response(execution))


# -- Execution reads -----------------------------------------------------------


@router.get(
    "/agents",
    response_model=AgentExecutionAgentListResponse,
)
def list_observed_agents(
    service: Annotated[AgentExecutionService, Depends(get_agent_execution_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> AgentExecutionAgentListResponse:
    """List agents represented by the tenant's execution evidence."""
    page = service.list_agents(offset=offset, limit=limit, context=context)
    return AgentExecutionAgentListResponse(
        items=[_agent_summary_to_response(item) for item in page.items],
        next_offset=page.next_offset,
    )


@router.get(
    "/{execution_id}",
    response_model=AgentExecutionDetailResponse,
)
def get_agent_execution(
    execution_id: str,
    service: Annotated[AgentExecutionService, Depends(get_agent_execution_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> AgentExecutionDetailResponse:
    """Return an execution detail with its full event timeline."""
    detail = service.get_execution_detail(execution_id, context)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution '{execution_id}' was not found.",
        )

    return AgentExecutionDetailResponse(
        execution=_execution_to_response(detail.execution),
        events=[_event_to_response(e) for e in detail.events],
        event_counts=detail.event_counts,
    )


@router.get(
    "",
    response_model=AgentExecutionListResponse,
)
def list_agent_executions(
    service: Annotated[AgentExecutionService, Depends(get_agent_execution_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    agent_id: str | None = Query(None, min_length=1, max_length=256),
    status_filter: str | None = Query(None, alias="status", min_length=1),
    runtime_provider: str | None = Query(None, min_length=1, max_length=128),
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    cursor: str | None = Query(None, max_length=512),
    limit: int = Query(20, ge=1, le=100),
) -> AgentExecutionListResponse:
    """List agent executions with cursor-based pagination."""
    status_value = None
    if status_filter is not None:
        try:
            status_value = AgentExecutionStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter '{status_filter}'.",
            )

    page = service.list_executions(
        agent_id=agent_id,
        status=status_value,
        runtime_provider=runtime_provider,
        created_after=created_after,
        created_before=created_before,
        cursor=cursor,
        limit=limit,
        context=context,
    )

    return AgentExecutionListResponse(
        items=[_summary_to_response(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{execution_id}/events",
    response_model=list[AgentExecutionEventResponse],
)
def list_agent_execution_events(
    execution_id: str,
    service: Annotated[AgentExecutionService, Depends(get_agent_execution_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    event_type: str | None = Query(None, min_length=1),
    limit: int = Query(100, ge=1, le=500),
) -> list[AgentExecutionEventResponse]:
    """List events for an execution, ordered by sequence number."""
    event_type_filter = None
    if event_type is not None:
        try:
            event_type_filter = EventType(event_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported event type '{event_type}'.",
            )

    events = service.list_events(
        execution_id, context, event_type=event_type_filter, limit=limit
    )
    return [_event_to_response(e) for e in events]


# -- Response mappers ----------------------------------------------------------


def _execution_to_response(execution: Any) -> Any:
    return AgentExecutionResponse(
        execution_id=execution.execution_id,
        agent_id=execution.agent_id,
        agent_name=execution.agent_name,
        agent_version=execution.agent_version,
        external_execution_id=execution.external_execution_id,
        runtime_provider=execution.runtime_provider,
        status=execution.status.value if hasattr(execution.status, "value") else execution.status,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        correlation_id=execution.correlation_id,
        parent_execution_id=execution.parent_execution_id,
        metadata=dict(execution.metadata) if hasattr(execution.metadata, "items") else execution.metadata,
        version=execution.version,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
    )


def _summary_to_response(item: Any) -> Any:
    return AgentExecutionSummaryResponse(
        execution_id=item.execution_id,
        agent_id=item.agent_id,
        agent_name=item.agent_name,
        runtime_provider=item.runtime_provider,
        external_execution_id=item.external_execution_id,
        status=item.status,
        started_at=item.started_at,
        completed_at=item.completed_at,
        event_count=item.event_count,
    )


def _agent_summary_to_response(item: Any) -> Any:
    return AgentExecutionAgentSummaryResponse(
        agent_id=item.agent_id,
        agent_name=item.agent_name,
        runtime_provider=item.runtime_provider,
        execution_count=item.execution_count,
        succeeded_count=item.succeeded_count,
        failed_count=item.failed_count,
        running_count=item.running_count,
        last_started_at=item.last_started_at,
    )


def _event_to_response(event: Any) -> Any:
    return AgentExecutionEventResponse(
        event_id=event.event_id,
        execution_id=event.execution_id,
        event_type=event.event_type.value if hasattr(event.event_type, "value") else event.event_type,
        sequence_number=event.sequence_number,
        occurred_at=event.occurred_at,
        received_at=event.received_at,
        late_for_runtime_findings=event.late_for_runtime_findings,
        runtime_findings_finalization_cutoff_at=event.runtime_findings_finalization_cutoff_at,
        runtime_findings_lateness_policy_hours=event.runtime_findings_lateness_policy_hours,
        correlation_id=event.correlation_id,
        causation_id=event.causation_id,
        actor_id=event.actor_id,
        actor_type=event.actor_type.value if event.actor_type and hasattr(event.actor_type, "value") else event.actor_type,
        step_id=event.workflow_step.step_id if event.workflow_step else None,
        step_name=event.workflow_step.step_name if event.workflow_step else None,
        lifecycle=(
            event.workflow_step.lifecycle.value if event.workflow_step else None
        ),
        parent_step_id=(
            event.workflow_step.parent_step_id if event.workflow_step else None
        ),
        source_kind=event.workflow_step.source_kind if event.workflow_step else None,
        resource_references=list(event.resource_references) if hasattr(event.resource_references, "__iter__") else [],
        evidence_references=list(event.evidence_references) if hasattr(event.evidence_references, "__iter__") else [],
        attributes=dict(event.attributes) if hasattr(event.attributes, "items") else event.attributes,
        event_schema_version=event.event_schema_version,
    )


# -- Dependency injection ------------------------------------------------------


def get_agent_execution_service() -> AgentExecutionService:
    """Return the cached agent execution service."""
    from ai_governance.api.dependencies.agent_execution import (
        get_agent_execution_service as _get_service,
    )
    return _get_service()
