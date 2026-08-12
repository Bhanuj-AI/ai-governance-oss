from __future__ import annotations

from datetime import UTC, datetime

from ai_governance.domain.evaluation_result import EvaluationMetric, EvaluationResult
from ai_governance.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
    Experiment,
    ExperimentStatus,
    Leaderboard,
)
from ai_governance.domain.jobs import Job, JobExecutionContext, JobStatus, JobType
from ai_governance.services.async_job_handlers import EvaluationJobHandler, ExperimentJobHandler


NOW = datetime(2026, 7, 17, tzinfo=UTC)
CONTEXT = JobExecutionContext("org-1", "project-1", "actor-1", "request-1")


class _Evaluations:
    def __init__(self) -> None:
        self.execution = None

    def submit_evaluation(self, execution, provider, **kwargs):
        self.execution = execution
        assert provider == "mock"
        assert kwargs["metric_specs"][0].name == "answer_relevance"
        return EvaluationResult(
            "evaluation-1",
            execution.execution_id,
            provider,
            "1",
            [EvaluationMetric("answer_relevance", 0.9)],
        )


class _Experiments:
    def __init__(self) -> None:
        self.called_with = None
        self.status = ExperimentStatus.RUNNING

    def get_experiment(self, experiment_id, **_kwargs):
        return Experiment(
            experiment_id,
            "Experiment",
            "Description",
            "owner",
            NOW,
            self.status,
            "org-1",
            "project-1",
        )

    def run_experiment(self, experiment_id, **kwargs):
        self.called_with = (experiment_id, kwargs)
        return [
            EvaluationRun(
                "run-1",
                experiment_id,
                "candidate-1",
                "dataset-1",
                "mock",
                "evaluation-1",
                NOW,
                NOW,
                EvaluationRunStatus.COMPLETED,
            )
        ], Leaderboard("leaderboard-1", experiment_id, "overall_score", NOW, [])


def test_evaluation_handler_executes_immutable_submission_snapshot() -> None:
    service = _Evaluations()
    outcome = EvaluationJobHandler(service).handle(
        _job(
            JobType.EVALUATION,
            {
                "workflow_id": "workflow-1",
                "execution_id": "execution-1",
                "workflow_name": "Workflow",
                "workflow_version": "1.0",
                "execution_status": "COMPLETED",
                "input": {"prompt": "hello"},
                "final_state": {"answer": "hello"},
                "events": [],
                "provider_name": "mock",
                "metric_specs": [{"name": "answer_relevance"}],
            },
        )
    )

    assert outcome.status is JobStatus.SUCCEEDED
    assert outcome.result_ref == "evaluation:evaluation-1"
    assert service.execution.organization_id == "org-1"


def test_experiment_handler_returns_generated_leaderboard_reference() -> None:
    service = _Experiments()
    outcome = ExperimentJobHandler(service).handle(
        _job(JobType.EXPERIMENT, {"experiment_id": "experiment-1"})
    )

    assert outcome.status is JobStatus.SUCCEEDED
    assert outcome.result_ref == "leaderboard:leaderboard-1"
    assert service.called_with[0] == "experiment-1"


def test_experiment_handler_cancels_a_job_for_a_cancelled_experiment() -> None:
    service = _Experiments()
    service.status = ExperimentStatus.CANCELLED

    outcome = ExperimentJobHandler(service).handle(
        _job(JobType.EXPERIMENT, {"experiment_id": "experiment-1"})
    )

    assert outcome.status is JobStatus.CANCELLED
    assert outcome.failure_reason == "Experiment cancellation requested."
    assert service.called_with is None


def _job(job_type: JobType, input_refs: dict[str, object]) -> Job:
    return Job(
        job_id="job-1",
        job_type=job_type,
        status=JobStatus.RUNNING,
        input_refs=input_refs,
        input_hash="hash-1",
        idempotency_key="key-1",
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
        execution_context=CONTEXT,
    )
