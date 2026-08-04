from datetime import UTC, datetime

from kavach.databases.postgres.database import PostgresDatabase
from kavach.domain.workflow_execution import WorkflowExecution
from kavach.repositories.postgres.postgres_replay_execution_store import (
    PostgresReplayExecutionStore,
)
from kavach.tenancy.domain import TenantContext


def test_execution_store_is_shared_by_independent_process_style_instances(
    postgres_database: PostgresDatabase,
) -> None:
    writer = PostgresReplayExecutionStore(postgres_database)
    reader = PostgresReplayExecutionStore(postgres_database)
    source = WorkflowExecution(
        workflow_id="workflow-1",
        execution_id="execution-1",
        workflow_name="Workflow",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={"input": True},
        final_state={"state": True},
        events=[{"type": "COMPLETED"}],
        organization_id="org-1",
        project_id="project-1",
        input_snapshot_ref="input:1",
        state_snapshot_ref="state:1",
        metadata={"source": "test"},
        created_at=datetime(2026, 7, 17, tzinfo=UTC),
    )

    writer.upsert(source)

    assert reader.get_execution(
        "execution-1", TenantContext("org-1", "project-1", "actor", "request")
    ) == source
    assert reader.get_execution(
        "execution-1",
        TenantContext("another-org", "project-1", "actor", "request"),
    ) is None
