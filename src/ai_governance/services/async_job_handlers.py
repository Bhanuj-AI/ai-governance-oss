"""Worker handlers for asynchronous Evaluation and Experiment submissions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ai_governance.domain.experiments import EvaluationRunStatus, ExperimentStatus
from ai_governance.domain.jobs import Job, JobResult, JobStatus
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation.evaluation_metrics import EvaluationMetricSpec
from ai_governance.tenancy.domain import TenantContext


class EvaluationJobHandler:
    """Execute an ``EVALUATION`` job using its immutable submission snapshot."""

    def __init__(self, evaluation_api_service: Any) -> None:
        self._evaluations = evaluation_api_service

    def handle(self, job: Job) -> JobResult:
        """Evaluate the captured execution and return its persisted result ID."""
        refs = job.input_refs
        execution = WorkflowExecution(
            workflow_id=_required(refs, "workflow_id"),
            execution_id=_required(refs, "execution_id"),
            workflow_name=str(refs.get("workflow_name") or refs["workflow_id"]),
            workflow_version=str(refs.get("workflow_version") or "unknown"),
            execution_status=_required(refs, "execution_status"),
            input=dict(refs.get("input") or {}),
            final_state=dict(refs.get("final_state") or {}),
            events=[dict(item) for item in refs.get("events") or []],
            organization_id=_context(job).organization_id,
            project_id=_context(job).project_id or "",
            metadata=dict(refs.get("metadata") or {}),
        )
        result = self._evaluations.submit_evaluation(
            execution,
            _required(refs, "provider_name"),
            metric_specs=_metric_specs(refs.get("metric_specs")),
            provider_config=dict(refs.get("provider_config") or {}),
            provider_installation_id=(
                str(refs["provider_installation_id"])
                if refs.get("provider_installation_id")
                else None
            ),
            context=_context(job),
        )
        return JobResult(
            job.job_id, JobStatus.SUCCEEDED, f"evaluation:{result.evaluation_id}", None
        )


class ExperimentJobHandler:
    """Execute an ``EXPERIMENT`` job through the Experiment application facade."""

    def __init__(self, experiment_api_service: Any) -> None:
        self._experiments = experiment_api_service

    def handle(self, job: Job) -> JobResult:
        """Run captured experiment inputs and retain the generated leaderboard."""
        refs = job.input_refs
        experiment_id = _required(refs, "experiment_id")
        if self._experiments.get_experiment(
            experiment_id, context=_context(job)
        ).status == ExperimentStatus.CANCELLED:
            return JobResult(
                job.job_id,
                JobStatus.CANCELLED,
                None,
                "Experiment cancellation requested.",
            )
        runs, leaderboard = self._experiments.run_experiment(
            experiment_id,
            metric_specs=_metric_specs(refs.get("metric_specs")),
            provider_config=dict(refs.get("provider_config") or {}),
            repetitions=int(refs.get("repetitions") or 1),
            context=_context(job),
        )
        if self._experiments.get_experiment(
            experiment_id, context=_context(job)
        ).status == ExperimentStatus.CANCELLED:
            return JobResult(
                job.job_id,
                JobStatus.CANCELLED,
                None,
                "Experiment cancellation requested.",
            )
        if any(
            run.status in (EvaluationRunStatus.FAILED, EvaluationRunStatus.EXECUTION_FAILED)
            for run in runs
        ):
            return JobResult(
                job.job_id,
                JobStatus.FAILED,
                None,
                "One or more experiment candidate evaluation runs failed.",
            )
        result_ref = (
            f"leaderboard:{leaderboard.leaderboard_id}"
            if leaderboard is not None
            else f"experiment:{experiment_id}"
        )
        return JobResult(job.job_id, JobStatus.SUCCEEDED, result_ref, None)


def _context(job: Job) -> TenantContext:
    if job.execution_context is None:
        raise ValueError("Asynchronous job is missing its tenant execution context.")
    context = job.execution_context
    return TenantContext(
        context.organization_id,
        context.project_id,
        context.actor_id,
        context.submitted_request_id,
        context.correlation_id,
    )


def _required(refs: Mapping[str, Any], key: str) -> str:
    value = str(refs.get(key) or "").strip()
    if not value:
        raise ValueError(f"Job input reference '{key}' is required.")
    return value


def _metric_specs(value: object) -> list[EvaluationMetricSpec]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("Job input reference 'metric_specs' must be a list.")
    return [
        EvaluationMetricSpec(
            name=str(item["name"]),
            description=item.get("description"),
            threshold=item.get("threshold"),
            weight=item.get("weight"),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in value
        if isinstance(item, Mapping)
    ]
