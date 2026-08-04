from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from kavach.domain.jobs import Job, JobExecutionContext, JobStatus, JobType
from kavach.domain.replay import Replay, ReplayConfiguration, ReplayMode
from kavach.repositories import InMemoryJobRepository
from kavach.services.replay_audit_service import ReplayAuditService
from kavach.tenancy.domain import TenantContext


class _ReplayReader:
    def __init__(self, replay: Replay) -> None:
        self._replay = replay

    def get(self, replay_id: str, context: TenantContext) -> Replay:
        assert replay_id == self._replay.replay_id
        assert context.organization_id == self._replay.organization_id
        assert context.project_id == self._replay.project_id
        return self._replay


def test_replay_audit_timeline_contains_only_this_replays_durable_work() -> None:
    now = datetime(2026, 8, 6, 5, 0, tzinfo=UTC)
    context = TenantContext("org-1", "project-1", "operator", "request-1", "corr-1")
    configuration = ReplayConfiguration(
        workflow_id="workflow-1",
        workflow_version="1.0.0",
        execution_adapter="historical",
        input_snapshot_ref="input:snapshot-1",
        state_snapshot_ref="state:snapshot-1",
        resolved_at=now + timedelta(seconds=1),
        configuration_hash="frozen-hash",
    )
    replay = Replay.create(
        replay_id="replay-1",
        source_execution_id="source-1",
        mode=ReplayMode.FULL,
        requested_by="operator",
        organization_id="org-1",
        project_id="project-1",
        request_id="request-1",
        correlation_id="corr-1",
        idempotency_key="idem-1",
        input_hash="input-hash",
        metadata={},
        now=now,
    )
    replay = replay.mark_ready(configuration, now + timedelta(seconds=1))
    replay = replay.mark_queued("execution-job", now + timedelta(seconds=2))
    replay = replay.mark_running(1, now + timedelta(seconds=3))
    replay = replay.reserve_replay_execution_id("execution-1", now + timedelta(seconds=4))
    replay = replay.mark_execution_completed(now + timedelta(seconds=5))
    replay = replay.mark_evaluating("evaluation-job", now + timedelta(seconds=6))
    replay = replay.record_replay_evaluation("replay-evaluation-1", now + timedelta(seconds=7))
    replay = replay.record_baseline_evaluation("baseline-evaluation-1", now + timedelta(seconds=8))
    replay = replay.mark_comparing(now + timedelta(seconds=9))
    replay = replay.record_comparison("comparison-1", now + timedelta(seconds=10))
    replay = replay.record_drift("drift-1", now + timedelta(seconds=11))
    replay = replay.mark_completed("result-1", now + timedelta(seconds=12))

    repository = InMemoryJobRepository()
    repository.save(_job("execution-job", JobType.REPLAY_EXECUTION, now, context))
    repository.save(
        _job("evaluation-job", JobType.REPLAY_EVALUATION, now + timedelta(seconds=6), context)
    )
    records = ReplayAuditService(
        replay_reader=_ReplayReader(replay), job_repository=repository
    ).list_records("replay-1", context)

    assert {record.operation_type for record in records} == {
        "FINALIZE_REPLAY",
        "ANALYZE_REPLAY_DRIFT",
        "COMPARE_REPLAY_EVALUATIONS",
        "RESOLVE_REPLAY_BASELINE",
        "REPLAY_EVALUATION",
        "SUBMIT_REPLAY_EVALUATION",
        "REPLAY_EXECUTION",
        "SUBMIT_REPLAY_EXECUTION",
        "FREEZE_SOURCE_EVIDENCE",
        "CREATE_REPLAY",
    }
    assert next(
        record for record in records if record.operation_type == "FINALIZE_REPLAY"
    ).result_reference == "replay_result:result-1"
    assert next(
        record for record in records if record.operation_type == "REPLAY_EVALUATION"
    ).job_id == "evaluation-job"
    assert all("replay-1" in record.event_id for record in records)


def _job(
    job_id: str, job_type: JobType, now: datetime, context: TenantContext
) -> Job:
    execution_context = JobExecutionContext(
        organization_id=context.organization_id,
        project_id=context.project_id or "",
        actor_id=context.actor_id,
        submitted_request_id=context.request_id,
        correlation_id=context.correlation_id,
    )
    queued = Job(
        job_id=job_id,
        job_type=job_type,
        status=JobStatus.QUEUED,
        input_refs={"replay_id": "replay-1"},
        input_hash=f"hash-{job_id}",
        idempotency_key=f"idem-{job_id}",
        submitted_by=context.actor_id,
        attempt_count=0,
        max_attempts=3,
        result_ref=None,
        failure_reason=None,
        leased_by=None,
        lease_expires_at=None,
        heartbeat_at=None,
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
        execution_context=execution_context,
    )
    return replace(
        queued,
        status=JobStatus.SUCCEEDED,
        attempt_count=1,
        result_ref=f"result:{job_id}",
        started_at=now + timedelta(seconds=1),
        completed_at=now + timedelta(seconds=2),
        updated_at=now + timedelta(seconds=2),
    )
