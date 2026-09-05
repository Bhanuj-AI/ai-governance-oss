from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

from ai_governance.domain.evaluation_result import EvaluationMetric, EvaluationResult
from ai_governance.domain.jobs import (
    Job,
    JobExecutionContext,
    JobResult,
    JobStatus,
    JobType,
)
from ai_governance.domain.replay import ReplayStatus
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.repositories.in_memory import InMemoryJobRepository
from ai_governance.repositories.in_memory_replay_repository import (
    InMemoryReplayRepository,
)
from ai_governance.repositories.in_memory_replay_result_repository import (
    InMemoryReplayResultRepository,
)
from ai_governance.services.job_api_service import JobApiService
from ai_governance.services.job_executor import JobExecutor
from ai_governance.services.replay_application_service import ReplayApplicationService
from ai_governance.services.replay_evaluation import ReplayEvaluationJobHandler
from ai_governance.services.replay_execution import (
    HistoricalReplayExecutionAdapter,
    ReplayExecutionAdapterRegistry,
    ReplayJobHandler,
)
from ai_governance.services.replay_execution_discovery import (
    InMemoryReplaySourceResolver,
)
from ai_governance.services.telemetry_service import TelemetryService
from ai_governance.tenancy.domain import TenantContext
from ai_governance.workers import JobWorker, replay_worker_runtime
from ai_governance.workers.replay_worker_runtime import _AutoEvaluationReplayHandler

NOW = datetime(2026, 7, 17, tzinfo=UTC)
CONTEXT = TenantContext("org-1", "project-1", "actor-1", "request-1")


class _Evaluations:
    def __init__(self) -> None:
        self.baseline = EvaluationResult(
            "baseline-1",
            "source-1",
            "mock",
            "1",
            [EvaluationMetric("quality", 0.8)],
            organization_id="org-1",
            project_id="project-1",
        )
        self.replay: EvaluationResult | None = None

    def submit_evaluation(self, execution, provider, context=None):
        assert provider == "mock"
        self.replay = EvaluationResult(
            "replay-evaluation-1",
            execution.execution_id,
            provider,
            "1",
            [EvaluationMetric("quality", 0.9)],
            organization_id=context.organization_id,
            project_id=context.project_id or "",
        )
        return self.replay

    def get_evaluation(self, evaluation_id, _context):
        return self.baseline if evaluation_id == self.baseline.evaluation_id else self.replay

    def get_history(self, _execution_id, _context):
        return [self.baseline]


def test_standalone_worker_uses_the_plugin_event_publisher(monkeypatch) -> None:
    """Worker lifecycle events use the generic publisher from extensions."""
    publisher = object()
    calls: list[str] = []

    class Registry:
        events = publisher

        def start(self) -> None:
            calls.append("start")

        def stop(self) -> None:
            calls.append("stop")

    class Runtime:
        def stop(self, *_args) -> None:
            return None

        def run_once(self) -> None:
            calls.append("run_once")

    def create_runtime(*, event_publisher):
        assert event_publisher is publisher
        return Runtime()

    monkeypatch.setattr(replay_worker_runtime, "create_plugin_registry", Registry)
    monkeypatch.setattr(
        replay_worker_runtime, "create_replay_worker_runtime", create_runtime
    )
    monkeypatch.setattr(replay_worker_runtime.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(sys, "argv", ["replay-worker", "--once"])

    replay_worker_runtime.main()

    assert calls == ["start", "run_once", "stop"]


def test_worker_wires_runtime_connections_into_async_experiments() -> None:
    """Async experiments enforce the same connection contract as REST runs."""

    runtime = replay_worker_runtime.create_replay_worker_runtime(
        worker_id="runtime-connection-test-worker"
    )
    experiment_handler = runtime._worker._executor._handlers[JobType.EXPERIMENT]

    assert experiment_handler._experiments._runtime_connection_service is not None


def test_worker_wires_a_real_telemetry_collector_into_async_evaluations() -> None:
    """Standalone workers must never receive a FastAPI ``Depends`` sentinel."""
    runtime = replay_worker_runtime.create_replay_worker_runtime(
        worker_id="telemetry-collector-test-worker"
    )
    evaluation_handler = runtime._worker._executor._handlers[JobType.EVALUATION]

    assert isinstance(evaluation_handler._evaluations._telemetry_collector, TelemetryService)


def test_worker_dispatches_replay_then_automatically_consumes_evaluation() -> None:
    jobs = InMemoryJobRepository()
    replays = InMemoryReplayRepository()
    results = InMemoryReplayResultRepository()
    store = InMemoryReplaySourceResolver()
    store.upsert(_source())
    application = ReplayApplicationService(
        replays,
        store,
        job_service=JobApiService(jobs),
        result_repository=results,
        id_generator=lambda: "replay-1",
        clock=lambda: NOW,
    )
    replay = application.create(
        source_execution_id="source-1",
        context=CONTEXT,
        idempotency_key="create-1",
        metadata={"evaluation_provider": "mock"},
    )
    queued = application.submit(replay.replay_id, CONTEXT)

    registry = ReplayExecutionAdapterRegistry()
    registry.register(HistoricalReplayExecutionAdapter())
    execution = ReplayJobHandler(
        replays,
        store,
        store,
        registry,
        execution_id_generator=lambda: "replayed-1",
        clock=lambda: NOW,
    )
    executor = JobExecutor(
        {
            JobType.REPLAY_EXECUTION: _AutoEvaluationReplayHandler(
                execution, replays, application, "mock"
            ),
            JobType.REPLAY_EVALUATION: ReplayEvaluationJobHandler(
                replay_repository=replays,
                result_repository=results,
                source_resolver=store,
                evaluation_api_service=_Evaluations(),
                clock=lambda: NOW,
                id_generator=lambda: "result-1",
            ),
        }
    )
    worker = JobWorker("replay-worker", jobs, executor)

    first = worker.run_once()
    after_execution = replays.get("replay-1", "org-1", "project-1")
    second = worker.run_once()
    completed = replays.get("replay-1", "org-1", "project-1")

    assert queued.status is ReplayStatus.QUEUED
    assert first is not None and first.status is JobStatus.SUCCEEDED
    assert after_execution is not None
    assert after_execution.status is ReplayStatus.EVALUATING
    assert after_execution.replay_execution_id == "replayed-1"
    assert after_execution.evaluation_job_id is not None
    assert second is not None and second.status is JobStatus.SUCCEEDED
    assert completed is not None and completed.status is ReplayStatus.COMPLETED
    assert len(jobs.list_jobs(job_type=JobType.REPLAY_EXECUTION)) == 1
    assert len(jobs.list_jobs(job_type=JobType.REPLAY_EVALUATION)) == 1


def test_controlled_replay_skips_generic_evaluation_and_finalizes_causal_audit() -> None:
    """Controlled evidence scores belong to Causal Audit, not Replay evaluation."""

    evaluation_calls: list[str] = []
    jobs = InMemoryJobRepository()
    replay = SimpleNamespace(
        replay_id="controlled-replay-1",
        status=ReplayStatus.EXECUTION_COMPLETED,
        controlled_evidence_intervention=object(),
        metadata={"causal_audit_id": "audit-1"},
    )

    class _ExecutionHandler:
        def handle(self, job):
            return JobResult(job.job_id, JobStatus.SUCCEEDED, "replay:ok", None)

    class _Replays:
        def get(self, *_args):
            return replay

    class _Application:
        def evaluate(self, *_args, **_kwargs):
            evaluation_calls.append("called")

    handler = _AutoEvaluationReplayHandler(
        _ExecutionHandler(),
        _Replays(),
        _Application(),
        "mock",
        JobApiService(jobs),
    )
    job = Job(
        job_id="replay-job-1",
        job_type=JobType.REPLAY_EXECUTION,
        status=JobStatus.RUNNING,
        input_refs={"replay_id": replay.replay_id},
        input_hash="hash",
        idempotency_key="replay-job-1",
        submitted_by="actor-1",
        attempt_count=1,
        max_attempts=3,
        result_ref=None,
        failure_reason=None,
        leased_by="worker-1",
        lease_expires_at=None,
        heartbeat_at=None,
        created_at=NOW,
        updated_at=NOW,
        started_at=NOW,
        completed_at=None,
        execution_context=JobExecutionContext(
            "org-1", "project-1", "actor-1", "request-1", None
        ),
    )

    assert handler.handle(job).status is JobStatus.SUCCEEDED
    assert evaluation_calls == []
    finalizations = jobs.list_jobs(job_type=JobType.CAUSAL_AUDIT)
    assert len(finalizations) == 1
    assert finalizations[0].input_refs == {
        "audit_id": "audit-1",
        "trigger_replay_id": "controlled-replay-1",
    }


def test_recovered_execution_job_reuses_its_reserved_execution_identity() -> None:
    jobs = InMemoryJobRepository()
    replays = InMemoryReplayRepository()
    store = InMemoryReplaySourceResolver()
    store.upsert(_source())
    application = ReplayApplicationService(
        replays,
        store,
        job_service=JobApiService(jobs),
        id_generator=lambda: "replay-1",
        clock=lambda: NOW,
    )
    replay = application.create(
        source_execution_id="source-1",
        context=CONTEXT,
        idempotency_key="create-1",
        metadata={"evaluation_provider": "mock"},
    )
    application.submit(replay.replay_id, CONTEXT)
    registry = ReplayExecutionAdapterRegistry()
    adapter = _CountingAdapter()
    registry.register(adapter)
    handler = ReplayJobHandler(
        replays,
        store,
        store,
        registry,
        execution_id_generator=lambda: "replayed-1",
        clock=lambda: NOW,
    )
    first_attempt = jobs.acquire_next_queued_job("interrupted-worker", 300)
    assert first_attempt is not None
    assert handler.handle(first_attempt).status is JobStatus.SUCCEEDED
    application.evaluate("replay-1", CONTEXT, evaluation_provider="mock")

    # Simulate a process dying after its handler persisted the execution but
    # before the worker acknowledged the job.  Lease recovery redelivers it.
    jobs.save(replace(first_attempt, lease_expires_at=NOW.replace(year=2020)))
    recovered = JobWorker(
        "recovery-worker", jobs, JobExecutor({JobType.REPLAY_EXECUTION: handler})
    ).run_once()
    persisted = replays.get("replay-1", "org-1", "project-1")

    assert recovered is not None and recovered.status is JobStatus.SUCCEEDED
    assert persisted is not None
    assert persisted.status is ReplayStatus.EVALUATING
    assert persisted.replay_execution_id == "replayed-1"
    assert adapter.calls == 1


def test_cancellation_is_observed_by_a_claimed_replay_handler() -> None:
    jobs = InMemoryJobRepository()
    replays = InMemoryReplayRepository()
    store = InMemoryReplaySourceResolver()
    store.upsert(_source())
    application = ReplayApplicationService(
        replays,
        store,
        job_service=JobApiService(jobs),
        id_generator=lambda: "replay-1",
        clock=lambda: NOW,
    )
    replay = application.create(
        source_execution_id="source-1", context=CONTEXT, idempotency_key="create-1"
    )
    queued = application.submit(replay.replay_id, CONTEXT)
    claimed = jobs.acquire_next_queued_job("worker", 300)
    assert claimed is not None
    application.cancel(queued.replay_id, CONTEXT)
    registry = ReplayExecutionAdapterRegistry()
    adapter = _CountingAdapter()
    registry.register(adapter)
    outcome = ReplayJobHandler(
        replays,
        store,
        store,
        registry,
        execution_id_generator=lambda: "replayed-1",
        clock=lambda: NOW,
    ).handle(claimed)

    assert outcome.status is JobStatus.CANCELLED
    assert adapter.calls == 0
    assert replays.get("replay-1", "org-1", "project-1").status is ReplayStatus.CANCELLED


def _source() -> WorkflowExecution:
    return WorkflowExecution(
        workflow_id="workflow-1",
        execution_id="source-1",
        workflow_name="Workflow",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={"message": "hello"},
        final_state={"answer": "hello"},
        events=[],
        organization_id="org-1",
        project_id="project-1",
        input_snapshot_ref="source:input:1",
        state_snapshot_ref="source:state:1",
    )


class _CountingAdapter(HistoricalReplayExecutionAdapter):
    name = "historical"

    def __init__(self) -> None:
        self.calls = 0

    def replay(self, source_execution, configuration, context):
        self.calls += 1
        return super().replay(source_execution, configuration, context)
