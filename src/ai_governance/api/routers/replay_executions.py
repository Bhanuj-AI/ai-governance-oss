"""Historical execution discovery for governed Replay creation."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ai_governance.api.dependencies import get_replay_execution_catalog
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models import (
    ReplayExecutionSearchItemResponse,
    ReplayExecutionSearchPageResponse,
)
from ai_governance.services.replay_execution_discovery import ReplayExecutionSearchFilters
from ai_governance.tenancy.domain import TenantContext


router = APIRouter(prefix="/api/v1/replay-executions", tags=["Replay executions"])


@router.get("/search", response_model=ReplayExecutionSearchPageResponse)
def search_replay_executions(
    catalog: Annotated[Any, Depends(get_replay_execution_catalog)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    query: str | None = Query(None, min_length=1, max_length=256),
    workflow_id: str | None = Query(None, min_length=1, max_length=256),
    execution_status: str | None = Query(None, alias="status", min_length=1),
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    replayable_only: bool = False,
    cursor: str | None = Query(None, max_length=512),
    limit: int = Query(20, ge=1, le=100),
) -> ReplayExecutionSearchPageResponse:
    """Search a tenant-scoped execution projection with an opaque cursor."""
    page = catalog.search(
        ReplayExecutionSearchFilters(
            query=query,
            workflow_id=workflow_id,
            status=execution_status,
            created_after=created_after,
            created_before=created_before,
            replayable_only=replayable_only,
            cursor=cursor,
            limit=limit,
        ),
        context,
    )
    return ReplayExecutionSearchPageResponse(
        items=[_to_response(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{execution_id}", response_model=ReplayExecutionSearchItemResponse)
def get_replay_execution(
    execution_id: str,
    catalog: Annotated[Any, Depends(get_replay_execution_catalog)],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> ReplayExecutionSearchItemResponse:
    """Return one eligible-source projection after tenant-scoped exact lookup."""
    projection = catalog.get(execution_id, context)
    if projection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution '{execution_id}' was not found.",
        )
    return _to_response(projection)


def _to_response(item: Any) -> ReplayExecutionSearchItemResponse:
    return ReplayExecutionSearchItemResponse(
        execution_id=item.execution_id,
        workflow_id=item.workflow_id,
        workflow_name=item.workflow_name,
        workflow_version=item.workflow_version,
        execution_status=item.execution_status,
        created_at=(
            item.created_at if hasattr(item, "created_at") else item.executed_at
        ),
        replayable=item.replayable,
        replayability_reason=getattr(
            item, "replayability_reason", getattr(item, "replayability_summary", None)
        ),
    )
