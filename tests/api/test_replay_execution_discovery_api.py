from datetime import UTC, datetime

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import (
    get_replay_execution_catalog,
    get_replay_source_resolver,
)
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.services.replay_execution_discovery import (
    InMemoryReplayExecutionCatalog,
    InMemoryReplaySourceResolver,
    projection_from_execution,
)


def test_execution_search_is_tenant_scoped_and_dry_run_resolves_selected_source() -> (
    None
):
    source = _execution("execution-1")
    other = _execution("other-project", project_id="project-other")
    catalog = InMemoryReplayExecutionCatalog(
        (
            projection_from_execution(source, replayable=True, now=source.created_at),
            projection_from_execution(other, replayable=True, now=other.created_at),
        )
    )
    source_resolver = InMemoryReplaySourceResolver()
    source_resolver.upsert(source)
    source_resolver.upsert(other)
    app = create_app()
    app.dependency_overrides[get_replay_execution_catalog] = lambda: catalog
    app.dependency_overrides[get_replay_source_resolver] = lambda: source_resolver
    client = TestClient(app)

    search = client.get(
        "/api/v1/replay-executions/search", params={"query": "execution"}
    )
    exact = client.get("/api/v1/replay-executions/execution-1")
    dry_run = client.post(
        "/api/v1/replays",
        json={
            "source_execution_id": "execution-1",
            "idempotency_key": "discovery-api-test",
            "dry_run": True,
        },
    )
    hidden = client.get("/api/v1/replay-executions/other-project")

    assert search.status_code == 200
    assert [item["execution_id"] for item in search.json()["items"]] == ["execution-1"]
    assert search.json()["items"][0]["replayable"] is True
    assert exact.status_code == 200
    assert exact.json()["execution_id"] == "execution-1"
    assert exact.json()["replayability_reason"] is None
    assert dry_run.status_code == 201
    assert dry_run.json()["configuration"]["workflow_id"] == "claims"
    assert hidden.status_code == 404


def _execution(
    execution_id: str, *, project_id: str = "project_default"
) -> WorkflowExecution:
    return WorkflowExecution(
        workflow_id="claims",
        execution_id=execution_id,
        workflow_name="Claims workflow",
        workflow_version="2026.1",
        execution_status="COMPLETED",
        input={"claim": execution_id},
        final_state={"result": "complete"},
        events=[],
        organization_id="org_default",
        project_id=project_id,
        execution_adapter="historical",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
