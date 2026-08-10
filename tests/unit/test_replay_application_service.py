from datetime import UTC, datetime

import pytest

from ai_governance.domain.replay import ReplayMode, ReplayStatus
from ai_governance.domain.jobs import Job, JobStatus, JobType
from ai_governance.domain.replay.errors import ReplayIdempotencyConflict
from ai_governance.domain.replay.errors import ReplayUnauthorized
from ai_governance.authorization.contracts import AuthorizationEnforcementDecision
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.repositories.in_memory_replay_repository import InMemoryReplayRepository
from ai_governance.services.replay_application_service import ReplayApplicationService
from ai_governance.tenancy.domain import TenantContext


class _SourceResolver:
    def __init__(self, source: WorkflowExecution | None) -> None:
        self.source = source

    def get_execution(
        self, execution_id: str, context: TenantContext
    ) -> WorkflowExecution | None:
        return (
            self.source
            if self.source and self.source.execution_id == execution_id
            else None
        )


def test_replay_creation_freezes_configuration_and_becomes_ready() -> None:
    service = _service(_execution())

    replay = service.create(
        source_execution_id="execution-1",
        context=_context(),
        idempotency_key="replay-1",
        metadata={"reason": "investigate"},
    )

    assert replay.status is ReplayStatus.READY
    assert replay.configuration is not None
    assert replay.configuration.workflow_version == "1.0.0"
    assert replay.configuration.input_snapshot_ref.startswith("inline:input:")
    with pytest.raises(TypeError):
        replay.configuration.runtime_parameters["temperature"] = 0.9  # type: ignore[index]


def test_missing_source_creates_a_queryable_failed_replay() -> None:
    repository = InMemoryReplayRepository()
    service = ReplayApplicationService(
        repository,
        _SourceResolver(None),
        id_generator=lambda: "replay-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )

    replay = service.create(
        source_execution_id="missing",
        context=_context(),
        idempotency_key="replay-1",
    )

    assert replay.status is ReplayStatus.FAILED
    assert replay.failure is not None
    assert repository.get("replay-1", "organization-1", "project-1") == replay


def test_replay_creation_is_tenant_scoped_and_idempotent() -> None:
    service = _service(_execution())
    first = service.create(
        source_execution_id="execution-1",
        context=_context(),
        idempotency_key="replay-1",
    )

    duplicate = service.create(
        source_execution_id="execution-1",
        context=_context(),
        idempotency_key="replay-1",
    )

    assert duplicate == first
    with pytest.raises(ReplayIdempotencyConflict):
        service.create(
            source_execution_id="another-execution",
            context=_context(),
            idempotency_key="replay-1",
        )


def test_ready_replay_can_be_archived_but_not_changed() -> None:
    service = _service(_execution())
    replay = service.create(
        source_execution_id="execution-1",
        context=_context(),
        idempotency_key="replay-1",
        mode=ReplayMode.FULL,
    )

    archived = service.archive(replay.replay_id, _context())

    assert archived.status is ReplayStatus.ARCHIVED
    assert archived.archived_at is not None
    assert service.get(replay.replay_id, _context()) == archived


def test_ready_replay_submission_is_idempotent_and_cancellable() -> None:
    job_service = _JobService()
    service = ReplayApplicationService(
        InMemoryReplayRepository(),
        _SourceResolver(_execution()),
        job_service=job_service,
        id_generator=lambda: "replay-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    replay = service.create(
        source_execution_id="execution-1",
        context=_context(),
        idempotency_key="replay-1",
    )

    queued = service.submit(replay.replay_id, _context())

    assert queued.status is ReplayStatus.QUEUED
    assert queued.job_id == "job-1"
    assert service.submit(replay.replay_id, _context()) == queued
    assert job_service.submissions == 1
    assert service.cancel(replay.replay_id, _context()).status is ReplayStatus.CANCELLED


def test_plugin_authorization_enforcer_runs_after_rbac_and_before_submission() -> None:
    job_service = _JobService()
    service = ReplayApplicationService(
        InMemoryReplayRepository(),
        _SourceResolver(_execution()),
        job_service=job_service,
        id_generator=lambda: "replay-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        authorization_enforcers=(_DenyReplayExecution(),),
    )
    replay = service.create(
        source_execution_id="execution-1", context=_context(), idempotency_key="replay-1"
    )

    with pytest.raises(ReplayUnauthorized, match="EXPLICIT_DENY_POLICY"):
        service.submit(replay.replay_id, _context())

    assert job_service.submissions == 0


class _DenyReplayExecution:
    def authorize(self, request):
        assert request.action == "replay.execute"
        assert request.resource.resource_id == "replay-1"
        return AuthorizationEnforcementDecision(False, "EXPLICIT_DENY_POLICY", "decision-1")


def _service(source: WorkflowExecution) -> ReplayApplicationService:
    return ReplayApplicationService(
        InMemoryReplayRepository(),
        _SourceResolver(source),
        id_generator=lambda: "replay-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )


def _execution() -> WorkflowExecution:
    return WorkflowExecution(
        workflow_id="workflow-1",
        execution_id="execution-1",
        workflow_name="workflow",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={"claim": "A"},
        final_state={"answer": "B"},
        events=[],
        organization_id="organization-1",
        project_id="project-1",
        runtime_parameters={"temperature": 0.2},
    )


def _context() -> TenantContext:
    return TenantContext(
        organization_id="organization-1",
        project_id="project-1",
        actor_id="actor-1",
        request_id="request-1",
    )


class _JobService:
    def __init__(self) -> None:
        self.submissions = 0

    def submit(self, submission) -> Job:
        self.submissions += 1
        return Job(
            job_id="job-1",
            job_type=submission.job_type,
            status=JobStatus.QUEUED,
            input_refs=submission.input_refs,
            input_hash="hash",
            idempotency_key=submission.idempotency_key,
            submitted_by=submission.submitted_by,
            attempt_count=0,
            max_attempts=submission.max_attempts,
            result_ref=None,
            failure_reason=None,
            leased_by=None,
            lease_expires_at=None,
            heartbeat_at=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            started_at=None,
            completed_at=None,
            execution_context=submission.execution_context,
        )

    def cancel(self, job_id: str, context: TenantContext) -> Job:
        return Job(
            job_id=job_id,
            job_type=JobType.REPLAY_EXECUTION,
            status=JobStatus.CANCELLED,
            input_refs={},
            input_hash="hash",
            idempotency_key="key",
            submitted_by=context.actor_id,
            attempt_count=0,
            max_attempts=3,
            result_ref=None,
            failure_reason=None,
            leased_by=None,
            lease_expires_at=None,
            heartbeat_at=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            started_at=None,
            completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
