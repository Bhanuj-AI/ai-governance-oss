import json
from datetime import UTC, datetime

import pytest

from ai_governance.api.mappers.replay_mapper import ReplayApiMapper
from ai_governance.authorization.contracts import AuthorizationEnforcementDecision
from ai_governance.domain.jobs import Job, JobStatus, JobType
from ai_governance.domain.replay import (
    ReplayManifest,
    ReplayManifestEligibility,
    ReplayManifestReason,
    ReplayManifestReasonCode,
    ReplayMode,
    ReplayStatus,
)
from ai_governance.domain.replay.errors import (
    ReplayIdempotencyConflict,
    ReplayUnauthorized,
)
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.repositories.in_memory_replay_repository import (
    InMemoryReplayRepository,
)
from ai_governance.repositories.mappers.replay_persistence_mapper import (
    ReplayPersistenceMapper,
)
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


def test_replay_configuration_round_trips_optional_manifest_and_legacy_records():
    source = _execution()
    manifest = ReplayManifest(
        source_execution_id="execution-1",
        source_execution_status="FAILED",
        eligibility=ReplayManifestEligibility.ELIGIBLE,
        tool_call_count=1,
        evidence_reference_count=1,
        runtime_type="external-runtime",
        adapter_id="external-runtime/v1",
        adapter_version="1",
        replay_reference="runtime://replays/execution-1",
        isolation_guarantee="isolated-runtime/v1",
    )
    source.metadata["replay_manifest"] = manifest.to_dict()
    source.execution_adapter = "external-runtime/v1"
    source.artifact_refs = ["runtime://replays/execution-1"]

    replay = _service(source).create(
        source_execution_id="execution-1",
        context=_context(),
        idempotency_key="replay-1",
    )
    assert replay.configuration is not None
    assert replay.configuration.replay_manifest == manifest

    response = ReplayApiMapper.to_response(replay)
    assert response.configuration is not None
    assert response.configuration.replay_manifest is not None
    assert response.configuration.replay_manifest.manifest_hash == manifest.manifest_hash

    record = ReplayPersistenceMapper.to_persistence_record(replay)
    restored = ReplayPersistenceMapper.from_persistence_record(record)
    assert restored.configuration is not None
    assert restored.configuration.replay_manifest == manifest

    # Existing persisted configurations had no manifest field. They remain
    # readable and do not acquire a retroactive eligibility classification.
    legacy_configuration = json.loads(record["configuration_json"])
    legacy_configuration.pop("replay_manifest")
    record["configuration_json"] = json.dumps(legacy_configuration)
    legacy = ReplayPersistenceMapper.from_persistence_record(record)
    assert legacy.configuration is not None
    assert legacy.configuration.replay_manifest is None


def test_ineligible_source_manifest_fails_closed_without_changing_legacy_sources():
    source = _execution()
    source.metadata["replay_manifest"] = ReplayManifest(
        source_execution_id="execution-1",
        source_execution_status="FAILED",
        eligibility=ReplayManifestEligibility.INELIGIBLE,
        tool_call_count=0,
        evidence_reference_count=0,
        reasons=(
            ReplayManifestReason(
                ReplayManifestReasonCode.MISSING_REPLAY_CAPABILITY,
                "Observed execution has no explicit replay capability.",
            ),
        ),
    ).to_dict()

    replay = _service(source).create(
        source_execution_id="execution-1",
        context=_context(),
        idempotency_key="replay-1",
    )

    assert replay.status is ReplayStatus.FAILED
    assert replay.failure is not None
    assert replay.failure.code == "ReplayNotReplayable"
    assert "MISSING_REPLAY_CAPABILITY" in replay.failure.message


def test_manifest_cannot_be_attached_to_a_different_source_execution():
    source = _execution()
    source.execution_adapter = "external-runtime/v1"
    source.artifact_refs = ["runtime://replays/execution-1"]
    source.metadata["replay_manifest"] = ReplayManifest(
        source_execution_id="another-execution",
        source_execution_status="FAILED",
        eligibility=ReplayManifestEligibility.ELIGIBLE,
        tool_call_count=1,
        evidence_reference_count=1,
        runtime_type="external-runtime",
        adapter_id="external-runtime/v1",
        adapter_version="1",
        replay_reference="runtime://replays/execution-1",
        isolation_guarantee="isolated-runtime/v1",
    ).to_dict()

    replay = _service(source).create(
        source_execution_id="execution-1",
        context=_context(),
        idempotency_key="replay-1",
    )

    assert replay.status is ReplayStatus.FAILED
    assert replay.failure is not None
    assert "belongs to another execution" in replay.failure.message


def test_tampered_manifest_version_fails_closed_before_replay_creation():
    source = _execution()
    source.execution_adapter = "external-runtime/v1"
    source.artifact_refs = ["runtime://replays/execution-1"]
    manifest = ReplayManifest(
        source_execution_id="execution-1",
        source_execution_status="FAILED",
        eligibility=ReplayManifestEligibility.ELIGIBLE,
        tool_call_count=1,
        evidence_reference_count=1,
        runtime_type="external-runtime",
        adapter_id="external-runtime/v1",
        adapter_version="1",
        replay_reference="runtime://replays/execution-1",
        isolation_guarantee="isolated-runtime/v1",
    ).to_dict()
    manifest["adapter_version"] = "2"
    source.metadata["replay_manifest"] = manifest

    replay = _service(source).create(
        source_execution_id="execution-1",
        context=_context(),
        idempotency_key="replay-1",
    )

    assert replay.status is ReplayStatus.FAILED
    assert replay.failure is not None
    assert replay.failure.message == "Source replay manifest is malformed."


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
