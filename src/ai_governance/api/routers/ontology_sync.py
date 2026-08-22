from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ai_governance.api.dependencies import get_ontology_sync_event_service
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models import (
    ErrorResponse,
    OntologySyncEventListResponse,
    OntologySyncEventResponse,
    OntologySyncMetricsResponse,
)
from ai_governance.ontology.synchronization import (
    OntologySyncEvent,
    OntologySyncEventFilter,
    OntologySyncEventService,
    OntologySyncEventStatus,
    OntologySyncMetrics,
)

router = APIRouter(
    prefix="/api/v1/ontology/synchronization/events",
    tags=["Ontology Synchronization"],
)


@router.get(
    "",
    response_model=OntologySyncEventListResponse,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse}},
    summary="List ontology sync events",
    description="List newest-first ontology synchronization events with bounded pagination and optional filters.",
)
def list_events(
    service: Annotated[
        OntologySyncEventService,
        Depends(get_ontology_sync_event_service),
    ],
    status_filter: Annotated[
        OntologySyncEventStatus | None,
        Query(alias="status"),
    ] = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    correlation_id: str | None = None,
    event_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context=Depends(get_compatible_tenant_context),
) -> OntologySyncEventListResponse:
    events = service.list_events(
        OntologySyncEventFilter(
            status=status_filter,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=correlation_id,
            event_type=event_type,
            organization_id=context.organization_id,
            project_id=context.project_id,
        ),
        limit=limit + 1,
        offset=offset,
    )
    return OntologySyncEventListResponse(
        events=[_to_response(event) for event in events[:limit]],
        limit=limit,
        offset=offset,
        has_more=len(events) > limit,
    )


@router.get(
    "/metrics",
    response_model=OntologySyncMetricsResponse,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse}},
    summary="Get ontology sync metrics",
    description="Return aggregate synchronization event metrics.",
)
def get_metrics(
    service: Annotated[
        OntologySyncEventService,
        Depends(get_ontology_sync_event_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> OntologySyncMetricsResponse:
    return _metrics_response(
        service.metrics(context.organization_id, context.project_id)
    )


@router.get(
    "/{event_id}",
    response_model=OntologySyncEventResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get ontology sync event",
    description="Return one synchronization event and its latest status.",
)
def get_event(
    event_id: str,
    service: Annotated[
        OntologySyncEventService,
        Depends(get_ontology_sync_event_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> OntologySyncEventResponse:
    return _to_response(_get_event(service, event_id, context))


@router.get(
    "/{event_id}/status",
    response_model=OntologySyncEventResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get ontology sync event status",
    description="Return one synchronization event status record.",
)
def get_event_status(
    event_id: str,
    service: Annotated[
        OntologySyncEventService,
        Depends(get_ontology_sync_event_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> OntologySyncEventResponse:
    return _to_response(_get_event(service, event_id, context))


@router.post(
    "/{event_id}/retry",
    response_model=OntologySyncEventResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Retry ontology sync event",
    description="Requeue a failed or dead-letter synchronization event.",
)
def retry_event(
    event_id: str,
    service: Annotated[
        OntologySyncEventService,
        Depends(get_ontology_sync_event_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> OntologySyncEventResponse:
    try:
        return _to_response(
            service.retry_event(event_id, context.organization_id, context.project_id)
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/{event_id}/cancel",
    response_model=OntologySyncEventResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Cancel ontology sync event",
    description="Cancel a pending synchronization event.",
)
def cancel_event(
    event_id: str,
    service: Annotated[
        OntologySyncEventService,
        Depends(get_ontology_sync_event_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> OntologySyncEventResponse:
    try:
        return _to_response(
            service.cancel_event(event_id, context.organization_id, context.project_id)
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


def _get_event(
    service: OntologySyncEventService,
    event_id: str,
    context,
) -> OntologySyncEvent:
    try:
        return service.get_event(event_id, context.organization_id, context.project_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


def _to_response(event: OntologySyncEvent) -> OntologySyncEventResponse:
    return OntologySyncEventResponse(
        event_id=event.event_id,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        scope_identifier=event.scope_identifier,
        correlation_id=event.correlation_id,
        payload=dict(event.payload),
        status=event.status,
        retry_count=event.retry_count,
        created_at=event.created_at,
        updated_at=event.updated_at,
        completed_at=event.completed_at,
        error_message=event.error_message,
        next_retry_at=event.next_retry_at,
        last_error=event.last_error,
        failed_at=event.failed_at,
        reconciliation_report=(
            dict(event.reconciliation_report)
            if event.reconciliation_report is not None
            else None
        ),
    )


def _metrics_response(
    metrics: OntologySyncMetrics,
) -> OntologySyncMetricsResponse:
    return OntologySyncMetricsResponse(**metrics.to_dict())
