from datetime import UTC, datetime, timedelta

from kavach.domain.workflow_execution import WorkflowExecution
from kavach.services.replay_execution_discovery import (
    InMemoryReplayExecutionCatalog,
    ReplayExecutionSearchFilters,
    projection_from_execution,
)
from kavach.tenancy.domain import TenantContext


def test_search_is_cursor_paginated_tenant_scoped_and_can_filter_replayability() -> (
    None
):
    catalog = InMemoryReplayExecutionCatalog(
        (
            _projection("execution-1", created_days_ago=1),
            _projection("execution-2", created_days_ago=2),
            _projection("execution-3", created_days_ago=3, replayable=False),
            _projection("other-tenant", created_days_ago=0, organization_id="other"),
        )
    )

    first = catalog.search(ReplayExecutionSearchFilters(limit=1), _context())
    second = catalog.search(
        ReplayExecutionSearchFilters(limit=1, cursor=first.next_cursor), _context()
    )
    replayable = catalog.search(
        ReplayExecutionSearchFilters(limit=10, replayable_only=True), _context()
    )
    recent = catalog.search(
        ReplayExecutionSearchFilters(
            limit=10,
            created_after=datetime(2026, 1, 8, tzinfo=UTC),
        ),
        _context(),
    )

    assert [item.execution_id for item in first.items] == ["execution-1"]
    assert [item.execution_id for item in second.items] == ["execution-2"]
    assert first.next_cursor is not None
    assert [item.execution_id for item in replayable.items] == [
        "execution-1",
        "execution-2",
    ]
    assert [item.execution_id for item in recent.items] == [
        "execution-1",
        "execution-2",
    ]
    assert catalog.get("other-tenant", _context()) is None


def _projection(
    execution_id: str,
    *,
    created_days_ago: int,
    organization_id: str = "org-1",
    replayable: bool = True,
) -> object:
    execution = WorkflowExecution(
        workflow_id="claims",
        execution_id=execution_id,
        workflow_name="Claims workflow",
        workflow_version="2026.1",
        execution_status="COMPLETED",
        input={"claim": execution_id},
        final_state={"result": "complete"},
        events=[],
        organization_id=organization_id,
        project_id="project-1",
        execution_adapter="historical",
        created_at=datetime(2026, 1, 10, tzinfo=UTC) - timedelta(days=created_days_ago),
    )
    return projection_from_execution(
        execution,
        replayable=replayable,
        now=execution.created_at,
    )


def _context() -> TenantContext:
    return TenantContext(
        organization_id="org-1",
        project_id="project-1",
        actor_id="actor-1",
        request_id="request-1",
    )
