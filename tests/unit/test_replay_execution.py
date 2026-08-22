from datetime import UTC, datetime

from ai_governance.domain.jobs import Job, JobExecutionContext, JobStatus, JobType
from ai_governance.domain.replay import ReplayMode, ReplayStatus
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.repositories.in_memory_replay_repository import (
    InMemoryReplayRepository,
)
from ai_governance.services.replay_application_service import ReplayApplicationService
from ai_governance.services.replay_execution import (
    ReplayExecutionAdapterRegistry,
    ReplayJobHandler,
)
from ai_governance.tenancy.domain import TenantContext


class _SourceResolver:
    def __init__(self, execution: WorkflowExecution) -> None:
        self.execution = execution

    def get_execution(self, execution_id: str, context: TenantContext):
        return self.execution if execution_id == self.execution.execution_id else None


class _Adapter:
    name = "historical"

    def validate_configuration(self, source_execution, configuration) -> None:
        return None

    def replay(self, source_execution, configuration, context):
        return WorkflowExecution(
            workflow_id=source_execution.workflow_id,
            execution_id=context.new_execution_id,
            workflow_name=source_execution.workflow_name,
            workflow_version=source_execution.workflow_version,
            execution_status="COMPLETED",
            input=dict(source_execution.input),
            final_state={"replayed": True},
            events=[],
        )


class _Store:
    def __init__(self) -> None:
        self.executions: list[WorkflowExecution] = []

    def save(self, execution: WorkflowExecution) -> None:
        self.executions.append(execution)


def test_replay_job_handler_persists_new_execution_and_lineage() -> None:
    source = WorkflowExecution(
        workflow_id="workflow-1",
        execution_id="source-1",
        workflow_name="workflow",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={"x": 1},
        final_state={},
        events=[],
        organization_id="organization-1",
        project_id="project-1",
    )
    repository = InMemoryReplayRepository()
    context = TenantContext("organization-1", "project-1", "actor-1", "request-1")
    replay = ReplayApplicationService(
        repository,
        _SourceResolver(source),
        id_generator=lambda: "replay-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    ).create(
        source_execution_id="source-1",
        context=context,
        idempotency_key="key-1",
        mode=ReplayMode.FULL,
    )
    replay = repository.update(
        replay.mark_queued("job-1", datetime(2026, 1, 1, tzinfo=UTC)), replay.version
    )
    registry = ReplayExecutionAdapterRegistry()
    registry.register(_Adapter())
    store = _Store()
    handler = ReplayJobHandler(
        repository,
        _SourceResolver(source),
        store,
        registry,
        execution_id_generator=lambda: "replay-execution-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = handler.handle(_job())

    assert result.status is JobStatus.SUCCEEDED
    assert store.executions[0].execution_id == "replay-execution-1"
    assert store.executions[0].metadata["source_execution_id"] == "source-1"
    assert (
        repository.get("replay-1", "organization-1", "project-1").status
        is ReplayStatus.EXECUTION_COMPLETED
    )


def _job() -> Job:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return Job(
        job_id="job-1",
        job_type=JobType.REPLAY_EXECUTION,
        status=JobStatus.RUNNING,
        input_refs={"replay_id": "replay-1"},
        input_hash="hash",
        idempotency_key="key",
        submitted_by="actor-1",
        attempt_count=1,
        max_attempts=3,
        result_ref=None,
        failure_reason=None,
        leased_by="worker-1",
        lease_expires_at=None,
        heartbeat_at=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=None,
        execution_context=JobExecutionContext(
            "organization-1", "project-1", "actor-1", "request-1"
        ),
    )
