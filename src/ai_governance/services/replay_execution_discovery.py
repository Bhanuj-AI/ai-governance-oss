"""Durable, tenant-scoped search projections for Replay source discovery.

Catalogs are deliberately not authoritative execution stores.  Replay creation
still resolves the full ``WorkflowExecution`` through its separate source
resolver and validates frozen evidence again on the server.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.tenancy.domain import TenantContext


@dataclass(frozen=True)
class ReplayExecutionProjection:
    """Lightweight execution inventory record; never stores workflow payloads."""

    execution_id: str
    organization_id: str
    project_id: str
    workflow_id: str
    workflow_name: str
    workflow_version: str
    execution_status: str
    executed_at: datetime
    completed_at: datetime | None
    actor_id: str | None
    actor_type: str | None
    replayable: bool
    replayability_code: str | None
    replayability_summary: str | None
    evaluation_available: bool
    created_at: datetime
    updated_at: datetime
    projection_version: int = 1


@dataclass(frozen=True)
class ReplayExecutionSearchFilters:
    query: str | None = None
    workflow_id: str | None = None
    status: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    replayable_only: bool = False
    cursor: str | None = None
    limit: int = 20


@dataclass(frozen=True)
class ReplayExecutionSearchItem:
    execution_id: str
    workflow_id: str
    workflow_name: str
    workflow_version: str
    execution_status: str
    created_at: datetime | None
    replayable: bool
    replayability_reason: str | None


@dataclass(frozen=True)
class ReplayExecutionSearchPage:
    items: tuple[ReplayExecutionSearchItem, ...]
    next_cursor: str | None
    has_more: bool = False


class ReplayExecutionCatalog(Protocol):
    """Portable persistence boundary for the Replay execution search projection."""

    def get(
        self, execution_id: str, context: TenantContext
    ) -> ReplayExecutionProjection | None: ...

    def search(
        self, filters: ReplayExecutionSearchFilters, context: TenantContext
    ) -> ReplayExecutionSearchPage: ...

    def upsert(
        self, projection: ReplayExecutionProjection, context: TenantContext
    ) -> ReplayExecutionProjection: ...

    def upsert_many(
        self, projections: tuple[ReplayExecutionProjection, ...], context: TenantContext
    ) -> int: ...

    def delete(self, execution_id: str, context: TenantContext) -> bool: ...


class InMemoryReplayExecutionCatalog:
    """Reference implementation used by unit tests and local/demo startup."""

    def __init__(self, projections: tuple[ReplayExecutionProjection, ...] = ()) -> None:
        self._projections: dict[tuple[str, str, str], ReplayExecutionProjection] = {}
        for projection in projections:
            context = TenantContext(
                organization_id=projection.organization_id,
                project_id=projection.project_id,
                actor_id="catalog-bootstrap",
                request_id="catalog-bootstrap",
            )
            self.upsert(projection, context)

    def get(
        self, execution_id: str, context: TenantContext
    ) -> ReplayExecutionProjection | None:
        return self._projections.get(_key(context, execution_id))

    def search(
        self, filters: ReplayExecutionSearchFilters, context: TenantContext
    ) -> ReplayExecutionSearchPage:
        projections = [
            projection
            for projection in self._projections.values()
            if projection.organization_id == context.organization_id
            and projection.project_id == (context.project_id or "")
            and _matches(projection, filters)
        ]
        projections.sort(
            key=lambda item: (item.executed_at, item.execution_id), reverse=True
        )
        cursor = _decode_cursor(filters.cursor) if filters.cursor else None
        if cursor:
            projections = [
                item for item in projections if _is_after_cursor(item, cursor)
            ]
        rows = projections[: filters.limit + 1]
        has_more = len(rows) > filters.limit
        rows = rows[: filters.limit]
        return ReplayExecutionSearchPage(
            items=tuple(_search_item(item) for item in rows),
            next_cursor=_encode_cursor(rows[-1]) if has_more and rows else None,
            has_more=has_more,
        )

    def upsert(
        self, projection: ReplayExecutionProjection, context: TenantContext
    ) -> ReplayExecutionProjection:
        _require_scope(projection, context)
        key = _key(context, projection.execution_id)
        existing = self._projections.get(key)
        if existing and (
            existing.workflow_id != projection.workflow_id
            or existing.workflow_version != projection.workflow_version
        ):
            raise ValueError(
                "Replay execution projection workflow identity is immutable."
            )
        self._projections[key] = projection
        return projection

    def upsert_many(
        self, projections: tuple[ReplayExecutionProjection, ...], context: TenantContext
    ) -> int:
        for projection in projections:
            self.upsert(projection, context)
        return len(projections)

    def delete(self, execution_id: str, context: TenantContext) -> bool:
        return self._projections.pop(_key(context, execution_id), None) is not None


class InMemoryReplaySourceResolver:
    """Authoritative local/dev resolver kept separate from the search projection."""

    def __init__(self) -> None:
        self._executions: dict[tuple[str, str, str], WorkflowExecution] = {}

    def upsert(self, execution: WorkflowExecution) -> None:
        self._executions[
            (execution.organization_id, execution.project_id, execution.execution_id)
        ] = execution

    def save(self, execution: WorkflowExecution) -> None:
        """Persist a produced execution through the same local store."""
        self.upsert(execution)

    def get_execution(
        self, execution_id: str, context: TenantContext
    ) -> WorkflowExecution | None:
        return self._executions.get(_key(context, execution_id))


def projection_from_execution(
    execution: WorkflowExecution,
    *,
    replayable: bool,
    replayability_code: str | None = None,
    replayability_summary: str | None = None,
    evaluation_available: bool = False,
    actor_id: str | None = None,
    actor_type: str | None = None,
    now: datetime | None = None,
) -> ReplayExecutionProjection:
    """Project compact discovery fields from an authoritative execution."""
    timestamp = now or datetime.now(UTC)
    executed_at = execution.created_at or timestamp
    return ReplayExecutionProjection(
        execution_id=execution.execution_id,
        organization_id=execution.organization_id,
        project_id=execution.project_id,
        workflow_id=execution.workflow_id,
        workflow_name=execution.workflow_name,
        workflow_version=execution.workflow_version,
        execution_status=execution.execution_status,
        executed_at=executed_at,
        completed_at=executed_at if execution.execution_status == "COMPLETED" else None,
        actor_id=actor_id,
        actor_type=actor_type,
        replayable=replayable,
        replayability_code=replayability_code,
        replayability_summary=replayability_summary,
        evaluation_available=evaluation_available,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _search_item(projection: ReplayExecutionProjection) -> ReplayExecutionSearchItem:
    return ReplayExecutionSearchItem(
        execution_id=projection.execution_id,
        workflow_id=projection.workflow_id,
        workflow_name=projection.workflow_name,
        workflow_version=projection.workflow_version,
        execution_status=projection.execution_status,
        created_at=projection.executed_at,
        replayable=projection.replayable,
        replayability_reason=projection.replayability_summary,
    )


def _matches(
    projection: ReplayExecutionProjection, filters: ReplayExecutionSearchFilters
) -> bool:
    query = (filters.query or "").strip().lower()
    if (
        query
        and query
        not in " ".join(
            (projection.execution_id, projection.workflow_id, projection.workflow_name)
        ).lower()
    ):
        return False
    if filters.workflow_id and projection.workflow_id != filters.workflow_id:
        return False
    if filters.status and projection.execution_status != filters.status:
        return False
    if filters.created_after and projection.executed_at < filters.created_after:
        return False
    if filters.created_before and projection.executed_at >= filters.created_before:
        return False
    return not filters.replayable_only or projection.replayable


def _key(context: TenantContext, execution_id: str) -> tuple[str, str, str]:
    return context.organization_id, context.project_id or "", execution_id


def _require_scope(
    projection: ReplayExecutionProjection, context: TenantContext
) -> None:
    if _key(context, projection.execution_id) != (
        projection.organization_id,
        projection.project_id,
        projection.execution_id,
    ):
        raise ValueError("Replay execution projection does not belong to the tenant.")


def _encode_cursor(projection: ReplayExecutionProjection) -> str:
    payload = json.dumps(
        {
            "executed_at": projection.executed_at.isoformat(),
            "execution_id": projection.execution_id,
        },
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        executed_at = datetime.fromisoformat(payload["executed_at"])
        return executed_at, str(payload["execution_id"])
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return None


def _is_after_cursor(
    projection: ReplayExecutionProjection, cursor: tuple[datetime, str]
) -> bool:
    executed_at, execution_id = cursor
    return projection.executed_at < executed_at or (
        projection.executed_at == executed_at and projection.execution_id < execution_id
    )
