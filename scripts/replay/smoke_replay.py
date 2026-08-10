#!/usr/bin/env python3
"""Exercise the governed Replay path locally."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from ai_governance.domain.evaluation_result import EvaluationMetric, EvaluationResult
from ai_governance.domain.jobs import Job, JobExecutionContext, JobStatus, JobType
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.repositories.in_memory_replay_repository import InMemoryReplayRepository
from ai_governance.repositories.in_memory_replay_result_repository import (
    InMemoryReplayResultRepository,
)
from ai_governance.services.replay_application_service import ReplayApplicationService
from ai_governance.services.replay_evaluation import ReplayEvaluationJobHandler
from ai_governance.services.replay_execution import (
    ReplayExecutionAdapterRegistry,
    ReplayJobHandler,
)
from ai_governance.tenancy.domain import TenantContext


NOW = datetime(2026, 1, 1, tzinfo=UTC)
CONTEXT = TenantContext("smoke-org", "smoke-project", "smoke-actor", "smoke-request")


class SourceStore:
    def __init__(self, source: WorkflowExecution) -> None:
        self.executions = {source.execution_id: source}

    def get_execution(self, execution_id: str, _context: TenantContext):
        return self.executions.get(execution_id)

    def save(self, execution: WorkflowExecution) -> None:
        self.executions[execution.execution_id] = execution


class HistoricalAdapter:
    name = "historical"

    def validate_configuration(self, _source, _configuration) -> None:
        return None

    def replay(self, source, _configuration, context):
        return WorkflowExecution(
            source.workflow_id,
            context.new_execution_id,
            source.workflow_name,
            source.workflow_version,
            "COMPLETED",
            dict(source.input),
            {"smoke_replayed": True},
            [],
            CONTEXT.organization_id,
            CONTEXT.project_id or "",
        )


class JobService:
    def __init__(self) -> None:
        self.submissions = 0

    def submit(self, _submission):
        self.submissions += 1
        job_id = "smoke-execution-job" if self.submissions == 1 else "smoke-evaluation-job"
        return type("SubmittedJob", (), {"job_id": job_id})()


class EvaluationApi:
    def __init__(self) -> None:
        self.baseline = EvaluationResult(
            "smoke-baseline-evaluation",
            "smoke-source-execution",
            "smoke-provider",
            "1",
            [EvaluationMetric("quality", 0.8)],
            organization_id=CONTEXT.organization_id,
            project_id=CONTEXT.project_id or "",
        )
        self.replay: EvaluationResult | None = None

    def submit_evaluation(self, execution, provider, context=None):
        assert provider == "smoke-provider"
        self.replay = EvaluationResult(
            "smoke-replay-evaluation",
            execution.execution_id,
            "smoke-provider",
            "1",
            [EvaluationMetric("quality", 0.9)],
            organization_id=context.organization_id,
            project_id=context.project_id or "",
        )
        return self.replay

    def get_evaluation(self, evaluation_id, _context):
        if evaluation_id == self.baseline.evaluation_id:
            return self.baseline
        assert self.replay is not None and evaluation_id == self.replay.evaluation_id
        return self.replay

    def get_history(self, execution_id, _context):
        assert execution_id == self.baseline.execution_id
        return [self.baseline]


def job(job_id: str, job_type: JobType, input_refs: dict[str, object]) -> Job:
    return Job(
        job_id,
        job_type,
        JobStatus.RUNNING,
        input_refs,
        "smoke-hash",
        f"smoke:{job_id}",
        CONTEXT.actor_id,
        1,
        3,
        None,
        None,
        "smoke-worker",
        None,
        None,
        NOW,
        NOW,
        NOW,
        None,
        JobExecutionContext(
            CONTEXT.organization_id,
            CONTEXT.project_id or "",
            CONTEXT.actor_id,
            CONTEXT.request_id,
        ),
    )


def main() -> None:
    source = WorkflowExecution(
        "smoke-workflow",
        "smoke-source-execution",
        "Replay smoke workflow",
        "1.0.0",
        "COMPLETED",
        {"prompt": "hello"},
        {"answer": "hello"},
        [],
        CONTEXT.organization_id,
        CONTEXT.project_id or "",
    )
    store = SourceStore(source)
    replays = InMemoryReplayRepository()
    results = InMemoryReplayResultRepository()
    service = ReplayApplicationService(
        replays,
        store,
        job_service=JobService(),
        result_repository=results,
        id_generator=lambda: "smoke-replay",
        clock=lambda: NOW,
    )

    replay = service.create(
        source_execution_id=source.execution_id,
        context=CONTEXT,
        idempotency_key="smoke-replay-create",
        metadata={"evaluation_provider": "smoke-provider"},
    )
    assert replay.status.value == "READY"

    replay = service.submit(replay.replay_id, CONTEXT)
    adapters = ReplayExecutionAdapterRegistry()
    adapters.register(HistoricalAdapter())
    execution = ReplayJobHandler(
        replays,
        store,
        store,
        adapters,
        execution_id_generator=lambda: "smoke-replay-execution",
        clock=lambda: NOW,
    ).handle(job(replay.job_id or "", JobType.REPLAY_EXECUTION, {"replay_id": replay.replay_id}))
    assert execution.status is JobStatus.SUCCEEDED

    replay = service.evaluate(replay.replay_id, CONTEXT, evaluation_provider="smoke-provider")
    evaluation = ReplayEvaluationJobHandler(
        replay_repository=replays,
        result_repository=results,
        source_resolver=store,
        evaluation_api_service=EvaluationApi(),
        clock=lambda: NOW,
        id_generator=lambda: "smoke-replay-result",
    ).handle(
        job(
            replay.evaluation_job_id or "",
            JobType.REPLAY_EVALUATION,
            {
                "replay_id": replay.replay_id,
                "evaluation_provider": "smoke-provider",
                "baseline_strategy": "LATEST_COMPATIBLE",
                "drift_threshold_policy": {"policy": "smoke"},
            },
        )
    )
    assert evaluation.status is JobStatus.SUCCEEDED
    result = service.get_result(replay.replay_id, CONTEXT)
    print(json.dumps({"replay_id": result.replay_id, "result_id": result.result_id, "status": "COMPLETED"}))


if __name__ == "__main__":
    main()
