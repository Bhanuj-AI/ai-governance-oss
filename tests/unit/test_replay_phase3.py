from datetime import UTC, datetime

from ai_governance.domain.jobs import Job, JobStatus
from ai_governance.domain.replay import ReplayStatus
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.repositories.in_memory_replay_repository import (
    InMemoryReplayRepository,
)
from ai_governance.repositories.in_memory_replay_result_repository import (
    InMemoryReplayResultRepository,
)
from ai_governance.services.replay_application_service import ReplayApplicationService
from ai_governance.services.replay_evaluation import ReplayEvaluationJobHandler
from ai_governance.tenancy.domain import TenantContext


class _Source:
    def __init__(self, *executions: WorkflowExecution) -> None:
        self.executions = {item.execution_id: item for item in executions}

    def get_execution(self, execution_id: str, _context):
        return self.executions.get(execution_id)


class _Jobs:
    def submit(self, _submission):
        return type("Submitted", (), {"job_id": "evaluation-job-1"})()


class _Evaluations:
    def __init__(self, baseline) -> None:
        self.baseline = baseline
        self.replay = None

    def submit_evaluation(self, execution, _provider, context=None):
        from ai_governance.domain.evaluation_result import (
            EvaluationMetric,
            EvaluationResult,
        )

        self.replay = EvaluationResult(
            "replay-evaluation-1", execution.execution_id, "provider", "1",
            [EvaluationMetric("quality", 0.9)], organization_id=context.organization_id,
            project_id=context.project_id or "",
        )
        return self.replay

    def get_evaluation(self, evaluation_id, _context):
        return self.baseline if evaluation_id == self.baseline.evaluation_id else self.replay

    def get_history(self, _execution_id, _context):
        return [self.baseline]


def test_replay_evaluation_job_completes_and_persists_immutable_result() -> None:
    from ai_governance.domain.evaluation_result import (
        EvaluationMetric,
        EvaluationResult,
    )

    now = datetime(2026, 1, 1, tzinfo=UTC)
    context = TenantContext("organization-1", "project-1", "actor-1", "request-1")
    source = _execution("source-1")
    replay_execution = _execution("replay-execution-1")
    replays = InMemoryReplayRepository()
    app = ReplayApplicationService(
        replays,
        _Source(source),
        job_service=_Jobs(),
        clock=lambda: now,
        id_generator=lambda: "replay-1",
    )
    replay = app.create(source_execution_id="source-1", context=context, idempotency_key="replay-1")
    replay = replays.update(replay.mark_queued("execution-job-1", now), replay.version)
    replay = replays.update(replay.mark_running(1, now), replay.version)
    replay = replays.update(replay.reserve_replay_execution_id("replay-execution-1", now), replay.version)
    replay = replays.update(replay.mark_execution_completed(now), replay.version)
    evaluating = app.evaluate(replay.replay_id, context, evaluation_provider="provider")
    baseline = EvaluationResult("baseline-1", "source-1", "provider", "1", [EvaluationMetric("quality", 0.8)], organization_id="organization-1", project_id="project-1")
    results = InMemoryReplayResultRepository()
    handler = ReplayEvaluationJobHandler(replay_repository=replays, result_repository=results, source_resolver=_Source(source, replay_execution), evaluation_api_service=_Evaluations(baseline), clock=lambda: now, id_generator=lambda: "result-1")

    outcome = handler.handle(_job(now))

    assert outcome.status is JobStatus.SUCCEEDED
    completed = replays.get(evaluating.replay_id, "organization-1", "project-1")
    assert completed.status is ReplayStatus.COMPLETED
    assert results.get_by_replay(completed.replay_id, "organization-1", "project-1").result_id == "result-1"


def _execution(execution_id: str) -> WorkflowExecution:
    return WorkflowExecution("workflow-1", execution_id, "workflow", "1", "COMPLETED", {"x": 1}, {}, [], "organization-1", "project-1")


def _job(now: datetime) -> Job:
    from ai_governance.domain.jobs import JobExecutionContext, JobType

    return Job("evaluation-job-1", JobType.REPLAY_EVALUATION, JobStatus.RUNNING, {"replay_id": "replay-1", "evaluation_provider": "provider", "baseline_strategy": "LATEST_COMPATIBLE"}, "hash", "key", "actor-1", 1, 3, None, None, None, None, None, now, now, now, None, JobExecutionContext("organization-1", "project-1", "actor-1", "request-1"))
