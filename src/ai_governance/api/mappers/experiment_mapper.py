from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_governance.api.models.evaluation import (
    EvaluationMetricResponse,
    EvaluationMetricSpecRequest,
)
from ai_governance.api.models.experiment import (
    EvaluationReportCallRoleResponse,
    EvaluationReportResponse,
    EvaluationReportRowResponse,
    EvaluationRunItemResultResponse,
    EvaluationRunResponse,
    EvaluationRunResultPageResponse,
    ExperimentCandidateComparisonResponse,
    ExperimentCandidateCreateRequest,
    ExperimentCandidateResponse,
    ExperimentResponse,
    ExperimentRunPlanResponse,
    ExperimentRunProgressResponse,
    ExperimentRunRequest,
    ExperimentRunResponse,
    LeaderboardEntryResponse,
    LeaderboardResponse,
)
from ai_governance.api.models.governance import EvaluationMetricComparisonResponse
from ai_governance.domain.experiments import (
    CandidateComparison,
    EvaluationRun,
    Experiment,
    ExperimentCandidate,
    Leaderboard,
    LeaderboardEntry,
)
from ai_governance.domain.jobs import JobSubmission, JobType
from ai_governance.evaluation.evaluation_metrics import EvaluationMetricSpec
from ai_governance.providers.provider_descriptor import scrub_sensitive_metadata
from ai_governance.services.experiment_api_service import (
    EvaluationReport,
    ExperimentRunEvaluationPage,
    ExperimentRunPlan,
)


class ExperimentApiMapper:
    """
    Converts experiment domain objects into stable REST DTOs.
    """

    @staticmethod
    def to_experiment_response(
        experiment: Experiment,
        metadata: Mapping[str, Any] | None = None,
    ) -> ExperimentResponse:
        """
        Convert an Experiment into its REST response representation.
        """
        return ExperimentResponse(
            experiment_id=experiment.experiment_id,
            name=experiment.name,
            description=experiment.description,
            owner=experiment.owner,
            status=experiment.status.value,
            created_at=experiment.created_at,
            updated_at=experiment.updated_at,
            metadata=_scrub_metadata(metadata or {}),
        )

    @staticmethod
    def to_candidate_response(
        candidate: ExperimentCandidate,
    ) -> ExperimentCandidateResponse:
        """
        Convert an ExperimentCandidate into its REST response representation.
        """
        return ExperimentCandidateResponse(
            candidate_id=candidate.candidate_id,
            experiment_id=candidate.experiment_id,
            candidate_name=candidate.name,
            prompt_id=candidate.prompt_id,
            prompt_version=candidate.prompt_version,
            model_id=candidate.model_id,
            model_version=candidate.model_version,
            dataset_id=candidate.dataset_id,
            dataset_version=candidate.dataset_version,
            provider_name=candidate.evaluation_provider,
            provider_installation_id=(
                str(candidate.metadata["provider_installation_id"])
                if candidate.metadata.get("provider_installation_id")
                else None
            ),
            runtime_connection_id=(
                str(candidate.metadata["runtime_connection_id"])
                if candidate.metadata.get("runtime_connection_id")
                else None
            ),
            runtime_parameters=_candidate_runtime_parameters(candidate),
            metadata=_scrub_metadata(candidate.metadata),
            created_at=candidate.created_at,
        )

    @staticmethod
    def to_candidate_comparison_response(
        comparison: CandidateComparison,
    ) -> ExperimentCandidateComparisonResponse:
        """
        Convert a candidate comparison into its REST response representation.
        """
        if comparison.baseline_candidate is None or comparison.candidate is None:
            raise ValueError("Candidate comparison is missing candidate configuration.")

        return ExperimentCandidateComparisonResponse(
            experiment_id=comparison.experiment_id or "",
            baseline_candidate=ExperimentApiMapper.to_candidate_response(
                comparison.baseline_candidate
            ),
            comparison_candidate=ExperimentApiMapper.to_candidate_response(
                comparison.candidate
            ),
            metric_comparisons=[
                EvaluationMetricComparisonResponse(
                    metric_name=metric.metric_name,
                    baseline_value=metric.baseline_value,
                    candidate_value=metric.candidate_value,
                    score_difference=metric.score_difference,
                )
                for metric in comparison.metric_comparisons
            ],
        )

    @staticmethod
    def to_evaluation_run_response(run: EvaluationRun) -> EvaluationRunResponse:
        return EvaluationRunResponse(
            run_id=run.run_id,
            experiment_id=run.experiment_id,
            candidate_id=run.candidate_id,
            dataset_version=run.dataset_version,
            provider_name=run.evaluation_provider,
            evaluation_result_id=run.evaluation_result_id,
            started_at=run.started_at,
            completed_at=run.completed_at,
            status=run.status.value,
            failure_reason=run.failure_reason,
            total_item_count=run.total_item_count,
            completed_item_count=run.completed_item_count,
            evaluated_item_count=run.evaluated_item_count,
            runner_provenance=(
                _scrub_metadata(run.runner_provenance)
                if run.runner_provenance is not None
                else None
            ),
        )

    @staticmethod
    def to_run_plan_response(plan: ExperimentRunPlan) -> ExperimentRunPlanResponse:
        """Convert the service-level run plan into its stable REST DTO."""
        return ExperimentRunPlanResponse(
            experiment_id=plan.experiment_id,
            candidate_count=plan.candidate_count,
            dataset_item_count=plan.dataset_item_count,
            runner_invocation_count=plan.runner_invocation_count,
            expected_sample_result_count=plan.expected_sample_result_count,
            workload_basis=plan.workload_basis,
            model_invocation_count=plan.model_invocation_count,
            evaluation_item_count=plan.evaluation_item_count,
            active_run=(
                ExperimentRunProgressResponse(
                    run_id=plan.active_run.run_id,
                    candidate_id=plan.active_run.candidate_id,
                    candidate_name=plan.active_run.candidate_name,
                    candidate_position=plan.active_run.candidate_position,
                    total_item_count=plan.active_run.total_item_count,
                    completed_item_count=plan.active_run.completed_item_count,
                    evaluated_item_count=plan.active_run.evaluated_item_count,
                )
                if plan.active_run is not None
                else None
            ),
        )

    @staticmethod
    def to_metric_specs(
        metric_specs: Sequence[EvaluationMetricSpecRequest],
    ) -> list[EvaluationMetricSpec]:
        """
        Convert REST metric specs into evaluation metric specs.
        """
        return [
            EvaluationMetricSpec(
                name=metric_spec.name,
                description=metric_spec.description,
                threshold=metric_spec.threshold,
                weight=metric_spec.weight,
                metadata=dict(metric_spec.metadata),
            )
            for metric_spec in metric_specs
        ]

    @staticmethod
    def candidate_runtime_parameters(
        request: ExperimentCandidateCreateRequest,
    ) -> dict[str, Any]:
        """
        Return candidate runtime parameters with stable defaults.
        """
        parameters = {
            "temperature": float(request.runtime_parameters.get("temperature", 0.0)),
            "top_p": float(request.runtime_parameters.get("top_p", 1.0)),
            "max_tokens": int(
                request.runtime_parameters.get(
                    "max_output_tokens",
                    request.runtime_parameters.get("max_tokens", 1024),
                )
            ),
        }
        return parameters

    @staticmethod
    def candidate_runtime_parameter_overrides(
        request: ExperimentCandidateCreateRequest,
    ) -> tuple[str, ...]:
        """Return the user-supplied controls without leaking them into payloads."""
        return tuple(
            sorted(
                {
                    "max_tokens" if name == "max_output_tokens" else name
                    for name in request.runtime_parameters
                    if name
                    in {"temperature", "top_p", "max_tokens", "max_output_tokens"}
                }
            )
        )

    @staticmethod
    def to_run_response(
        experiment_id: str,
        runs: Sequence[EvaluationRun],
        leaderboard: Leaderboard | None = None,
    ) -> ExperimentRunResponse:
        """
        Convert evaluation runs and optional leaderboard into a REST response.
        """
        return ExperimentRunResponse(
            experiment_id=experiment_id,
            runs=[
                EvaluationRunResponse(
                    run_id=run.run_id,
                    experiment_id=run.experiment_id,
                    candidate_id=run.candidate_id,
                    dataset_version=run.dataset_version,
                    provider_name=run.evaluation_provider,
                    evaluation_result_id=run.evaluation_result_id,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                    status=run.status.value,
                    failure_reason=run.failure_reason,
                    total_item_count=run.total_item_count,
                    completed_item_count=run.completed_item_count,
                    evaluated_item_count=run.evaluated_item_count,
                    runner_provenance=(
                        _scrub_metadata(run.runner_provenance)
                        if run.runner_provenance is not None
                        else None
                    ),
                )
                for run in runs
            ],
            leaderboard=(
                ExperimentApiMapper.to_leaderboard_response(leaderboard)
                if leaderboard is not None
                else None
            ),
        )

    @staticmethod
    def to_run_evaluation_page_response(
        result_page: ExperimentRunEvaluationPage,
    ) -> EvaluationRunResultPageResponse:
        """Map persisted item results without exposing execution payloads."""
        return EvaluationRunResultPageResponse(
            run_id=result_page.run_id,
            page=result_page.page,
            page_size=result_page.page_size,
            total_items=result_page.total_items,
            items=[
                EvaluationRunItemResultResponse(
                    evaluation_id=result.evaluation_id,
                    execution_id=result.execution_id,
                    evaluator_type=result.evaluator_type,
                    evaluator_version=result.evaluator_version,
                    created_at=result.created_at,
                    model_latency_ms=_model_latency_ms(result.metadata),
                    metrics=[
                        EvaluationMetricResponse(
                            name=metric.metric_name,
                            score=metric.metric_value,
                            explanation=None,
                        )
                        for metric in result.metrics
                    ],
                )
                for result in result_page.items
            ],
        )

    @staticmethod
    def to_evaluation_report_response(report: EvaluationReport) -> EvaluationReportResponse:
        """Map generic, persisted evaluation evidence into the REST report."""
        return EvaluationReportResponse(
            experiment_id=report.experiment_id,
            group_dimension=report.group_dimension,
            rows=[
                EvaluationReportRowResponse(
                    candidate_id=row.candidate_id,
                    candidate_name=row.candidate_name,
                    group=row.group,
                    sample_count=row.sample_count,
                    pass_rate=row.pass_rate,
                    metrics=dict(row.metrics),
                    original_task_tokens=row.original_task_tokens,
                    tokenizer=row.tokenizer,
                    token_count_kind=row.token_count_kind,
                    failure_categories=dict(row.failure_categories),
                    failed_scenario_ids=list(row.failed_scenario_ids),
                    call_roles=[
                        EvaluationReportCallRoleResponse(
                            call_role=call.call_role,
                            call_count=call.call_count,
                            input_tokens=call.input_tokens,
                            output_tokens=call.output_tokens,
                            total_tokens=call.total_tokens,
                            duration_ms=call.duration_ms,
                            original_task_included=call.original_task_included,
                            prior_conversation_retained=call.prior_conversation_retained,
                        )
                        for call in row.call_roles
                    ],
                    provider_cost=row.provider_cost,
                )
                for row in report.rows
            ],
            runner_provenance={
                candidate_id: [_scrub_metadata(item) for item in items]
                for candidate_id, items in report.runner_provenance.items()
            },
        )

    @staticmethod
    def to_run_job_submission(
        experiment_id: str,
        request: ExperimentRunRequest,
    ) -> JobSubmission:
        """
        Convert an async experiment run request into a job submission.
        """
        submitted_by = request.submitted_by or request.requested_by
        if request.idempotency_key is None or submitted_by is None:
            raise ValueError(
                "idempotency_key and submitted_by are required for async runs."
            )

        return JobSubmission(
            job_type=JobType.EXPERIMENT,
            input_refs={
                "operation": "experiment.run_async",
                "request_id": request.request_id,
                "correlation_id": (request.correlation_id or request.request_id),
                "experiment_id": experiment_id,
                "metric_specs": [
                    metric.model_dump(mode="json") for metric in request.metric_specs
                ],
                "provider_config": dict(request.provider_config),
                "repetitions": request.repetitions,
                "metadata": dict(request.metadata),
                "requested_by": request.requested_by,
                "actor_type": request.actor_type,
                "reason": request.reason,
            },
            idempotency_key=request.idempotency_key,
            submitted_by=submitted_by,
            max_attempts=request.max_attempts,
        )

    @staticmethod
    def to_leaderboard_response(
        leaderboard: Leaderboard,
    ) -> LeaderboardResponse:
        """
        Convert a Leaderboard into its REST response representation.
        """
        return LeaderboardResponse(
            leaderboard_id=leaderboard.leaderboard_id,
            experiment_id=leaderboard.experiment_id,
            ranking_strategy=leaderboard.ranking_strategy,
            generated_at=leaderboard.generated_at,
            entries=[
                LeaderboardEntryResponse(
                    rank=entry.rank,
                    candidate_id=entry.candidate_id,
                    overall_score=_observable_ranking_value(entry),
                    metrics=dict(entry.metrics),
                    cost=entry.metrics.get("estimated_model_cost"),
                    latency=entry.metrics.get("wall_clock_duration_seconds"),
                    reason=_observable_ranking_reason(
                        entry, leaderboard.ranking_strategy
                    ),
                )
                for entry in leaderboard.entries
            ],
        )


def _scrub_metadata(
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return scrub_sensitive_metadata(dict(metadata))


def _observable_ranking_value(entry: LeaderboardEntry) -> float:
    """Prefer persisted quality evidence over legacy composite snapshots."""
    for metric_name in ("overall_score", "score", "pass"):
        value = entry.metrics.get(metric_name)
        if value is not None:
            return value
    return entry.overall_score


def _observable_ranking_reason(
    entry: LeaderboardEntry,
    ranking_strategy: str,
) -> str:
    if ranking_strategy == "overall_score" and any(
        name in entry.metrics for name in ("overall_score", "score", "pass")
    ):
        return "Ranked by average quality metric score."
    return entry.reason


def _candidate_runtime_parameters(candidate: ExperimentCandidate) -> dict[str, Any]:
    overrides = candidate.metadata.get("runtime_parameter_overrides")
    if not isinstance(overrides, list):
        return {
            "temperature": candidate.temperature,
            "top_p": candidate.top_p,
            "max_tokens": candidate.max_tokens,
        }
    values = {
        "temperature": candidate.temperature,
        "top_p": candidate.top_p,
        "max_tokens": candidate.max_tokens,
    }
    return {name: values[name] for name in overrides if name in values}


def _model_latency_ms(metadata: Mapping[str, Any]) -> int | None:
    value = metadata.get("model_latency_ms")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
