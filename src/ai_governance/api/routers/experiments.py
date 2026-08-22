from __future__ import annotations

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from ai_governance.api.dependencies import (
    get_experiment_api_service,
    get_experiment_insight_service,
    get_job_api_service,
)
from ai_governance.api.dependencies.settings_control import get_configuration_service
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.mappers import (
    ExperimentApiMapper,
    GovernanceInsightApiMapper,
    JobApiMapper,
)
from ai_governance.api.models import (
    ErrorResponse,
    EvaluationRunResponse,
    EvaluationRunResultPageResponse,
    ExperimentCandidateComparisonResponse,
    ExperimentCandidateCreateRequest,
    ExperimentCandidateResponse,
    ExperimentCreateRequest,
    ExperimentResponse,
    ExperimentRunPlanResponse,
    ExperimentRunRequest,
    ExperimentRunResponse,
    GovernanceInsightResponse,
    JobResponse,
    LeaderboardResponse,
)
from ai_governance.domain.jobs import JobExecutionContext
from ai_governance.settings_control.operational import setting_context

router = APIRouter(
    prefix="/api/v1/experiments",
    tags=["Experiments"],
)


@router.post(
    "",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Create experiment",
    description="Create a draft experiment.",
)
def create_experiment(
    request: ExperimentCreateRequest,
    experiment_api_service: Annotated[
        object,
        Depends(get_experiment_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> ExperimentResponse:
    """
    Create a draft experiment.
    """
    experiment = experiment_api_service.create_experiment(
        name=request.name,
        description=request.description,
        metadata=request.metadata,
        context=context,
    )
    return ExperimentApiMapper.to_experiment_response(
        experiment,
        metadata=request.metadata,
    )


@router.get(
    "",
    response_model=list[ExperimentResponse],
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="List experiments",
    description="Return experiments visible through the REST control plane.",
)
def list_experiments(
    experiment_api_service: Annotated[
        object,
        Depends(get_experiment_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> list[ExperimentResponse]:
    """
    Return persisted experiments.
    """
    return [
        ExperimentApiMapper.to_experiment_response(experiment)
        for experiment in experiment_api_service.list_experiments(context)
    ]


@router.post(
    "/{experiment_id}/cancel",
    response_model=ExperimentResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Cancel experiment",
    description=(
        "Cancel a running experiment. Existing execution evidence is retained, "
        "and active evaluation runs are terminally recorded as cancelled."
    ),
)
def cancel_experiment(
    experiment_id: str,
    experiment_api_service: Annotated[
        object,
        Depends(get_experiment_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> ExperimentResponse:
    """Cancel a running experiment through the tenant-scoped control plane."""
    return ExperimentApiMapper.to_experiment_response(
        experiment_api_service.cancel_experiment(experiment_id, context)
    )


@router.get(
    "/{experiment_id}",
    response_model=ExperimentResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get experiment",
    description="Return an experiment by ID.",
)
def get_experiment(
    experiment_id: str,
    experiment_api_service: Annotated[
        object,
        Depends(get_experiment_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> ExperimentResponse:
    """
    Return an experiment by ID.
    """
    return ExperimentApiMapper.to_experiment_response(
        experiment_api_service.get_experiment(experiment_id, context)
    )


@router.get(
    "/{experiment_id}/candidates",
    response_model=list[ExperimentCandidateResponse],
    status_code=status.HTTP_200_OK,
)
def list_candidates(
    experiment_id: str,
    experiment_api_service: Annotated[object, Depends(get_experiment_api_service)],
    context=Depends(get_compatible_tenant_context),
) -> list[ExperimentCandidateResponse]:
    return [
        ExperimentApiMapper.to_candidate_response(candidate)
        for candidate in experiment_api_service.list_candidates(experiment_id, context)
    ]


@router.get(
    "/{experiment_id}/runs",
    response_model=list[EvaluationRunResponse],
    status_code=status.HTTP_200_OK,
)
def list_runs(
    experiment_id: str,
    experiment_api_service: Annotated[object, Depends(get_experiment_api_service)],
    context=Depends(get_compatible_tenant_context),
) -> list[EvaluationRunResponse]:
    return [
        ExperimentApiMapper.to_evaluation_run_response(run)
        for run in experiment_api_service.list_evaluation_runs(experiment_id, context)
    ]


@router.get(
    "/{experiment_id}/runs/{run_id}/evaluations",
    response_model=EvaluationRunResultPageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
    summary="List persisted item evaluations for a run",
    description=(
        "Return a tenant-scoped, paginated inventory of evaluator scores. "
        "Partial and cancelled runs retain completed item evidence."
    ),
)
def list_run_evaluations(
    experiment_id: str,
    run_id: str,
    experiment_api_service: Annotated[object, Depends(get_experiment_api_service)],
    context=Depends(get_compatible_tenant_context),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> EvaluationRunResultPageResponse:
    """Return safe per-item score evidence for one selected evaluation run."""
    return ExperimentApiMapper.to_run_evaluation_page_response(
        experiment_api_service.list_run_evaluations(
            experiment_id,
            run_id,
            page=page,
            page_size=page_size,
            context=context,
        )
    )


@router.get(
    "/{experiment_id}/run-plan",
    response_model=ExperimentRunPlanResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
    summary="Get experiment run plan",
    description=(
        "Return the declared candidate and dataset execution volume, plus "
        "persisted progress for any active candidate run."
    ),
)
def get_run_plan(
    experiment_id: str,
    experiment_api_service: Annotated[object, Depends(get_experiment_api_service)],
    context=Depends(get_compatible_tenant_context),
) -> ExperimentRunPlanResponse:
    """Return the tenant-scoped plan before, during, or after an experiment run."""
    return ExperimentApiMapper.to_run_plan_response(
        experiment_api_service.get_run_plan(experiment_id, context)
    )


@router.get(
    "/{experiment_id}/comparison",
    response_model=ExperimentCandidateComparisonResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Compare experiment candidates",
    description="Compare candidate configuration and latest evaluation metrics.",
)
def compare_experiment_candidates(
    experiment_id: str,
    experiment_api_service: Annotated[
        object,
        Depends(get_experiment_api_service),
    ],
    baseline_candidate_id: str = Query(..., min_length=1),
    comparison_candidate_id: str = Query(..., min_length=1),
    context=Depends(get_compatible_tenant_context),
) -> ExperimentCandidateComparisonResponse:
    """Return a backend-backed comparison for two candidates."""
    return ExperimentApiMapper.to_candidate_comparison_response(
        experiment_api_service.compare_candidates(
            experiment_id=experiment_id,
            baseline_candidate_id=baseline_candidate_id,
            comparison_candidate_id=comparison_candidate_id,
            context=context,
        )
    )


@router.get(
    "/{experiment_id}/insights",
    response_model=GovernanceInsightResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Summarize experiment insights",
    description="Explain experiment outcome evidence and trade-offs.",
)
def get_experiment_insights(
    experiment_id: str,
    insight_service: Annotated[
        object,
        Depends(get_experiment_insight_service),
    ],
    experiment_api_service: Annotated[object, Depends(get_experiment_api_service)],
    context=Depends(get_compatible_tenant_context),
) -> GovernanceInsightResponse:
    """
    Return evidence-first insights for an experiment.
    """
    experiment_api_service.get_experiment(experiment_id, context)
    return GovernanceInsightApiMapper.to_insight_response(
        insight_service.summarize_experiment(experiment_id)
    )


@router.get(
    "/{experiment_id}/comparative-insights",
    response_model=GovernanceInsightResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Compare experiment candidates",
    description="Explain which candidate evidence drove the comparison.",
)
def get_experiment_comparative_insights(
    experiment_id: str,
    insight_service: Annotated[
        object,
        Depends(get_experiment_insight_service),
    ],
    experiment_api_service: Annotated[object, Depends(get_experiment_api_service)],
    context=Depends(get_compatible_tenant_context),
) -> GovernanceInsightResponse:
    """
    Return comparative candidate insights for an experiment.
    """
    experiment_api_service.get_experiment(experiment_id, context)
    return GovernanceInsightApiMapper.to_insight_response(
        insight_service.compare_candidates(experiment_id)
    )


@router.get(
    "/{experiment_id}/candidates/{candidate_id}/insights",
    response_model=GovernanceInsightResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Explain candidate",
    description="Explain candidate evidence within an experiment.",
)
def get_candidate_insights(
    experiment_id: str,
    candidate_id: str,
    insight_service: Annotated[
        object,
        Depends(get_experiment_insight_service),
    ],
    experiment_api_service: Annotated[object, Depends(get_experiment_api_service)],
    context=Depends(get_compatible_tenant_context),
) -> GovernanceInsightResponse:
    """
    Return evidence-first insights for one experiment candidate.
    """
    experiment_api_service.get_experiment(experiment_id, context)
    return GovernanceInsightApiMapper.to_insight_response(
        insight_service.explain_candidate(
            experiment_id=experiment_id,
            candidate_id=candidate_id,
        )
    )


@router.post(
    "/{experiment_id}/candidates",
    response_model=ExperimentCandidateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Add candidate",
    description="Register a candidate for an experiment.",
)
def add_candidate(
    experiment_id: str,
    request: ExperimentCandidateCreateRequest,
    experiment_api_service: Annotated[
        object,
        Depends(get_experiment_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> ExperimentCandidateResponse:
    """
    Register a candidate for an experiment.
    """
    candidate = experiment_api_service.add_candidate(
        experiment_id=experiment_id,
        candidate_name=request.candidate_name,
        prompt_reference=request.prompt_version,
        model_reference=request.model_version,
        dataset_reference=request.dataset_version,
        provider_name=request.provider_name,
        provider_installation_id=request.provider_installation_id,
        runtime_connection_id=request.runtime_connection_id,
        runtime_parameters=(ExperimentApiMapper.candidate_runtime_parameters(request)),
        runtime_parameter_overrides=(
            ExperimentApiMapper.candidate_runtime_parameter_overrides(request)
        ),
        metadata=request.metadata,
        context=context,
    )
    return ExperimentApiMapper.to_candidate_response(candidate)


@router.post(
    "/{experiment_id}/run",
    response_model=ExperimentRunResponse | JobResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Run experiment",
    description="Execute an experiment synchronously.",
)
def run_experiment(
    experiment_id: str,
    request: ExperimentRunRequest,
    experiment_api_service: Annotated[
        object,
        Depends(get_experiment_api_service),
    ],
    job_api_service: Annotated[
        object,
        Depends(get_job_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
    configuration_service=Depends(get_configuration_service),
) -> ExperimentRunResponse | JobResponse:
    """
    Execute an experiment synchronously.
    """
    if request.is_async_submission:
        if "max_attempts" not in request.model_fields_set:
            request = request.model_copy(
                update={
                    "max_attempts": int(
                        configuration_service.get(
                            "jobs.retry_attempts", setting_context(context)
                        )
                    )
                }
            )
        submission = ExperimentApiMapper.to_run_job_submission(experiment_id, request)
        submission = replace(
            submission,
            execution_context=JobExecutionContext(
                context.organization_id,
                context.project_id or "",
                context.actor_id,
                context.request_id,
                context.correlation_id,
            ),
        )
        return JobApiMapper.to_response(job_api_service.submit(submission))

    runs, leaderboard = experiment_api_service.run_experiment(
        experiment_id=experiment_id,
        metric_specs=ExperimentApiMapper.to_metric_specs(request.metric_specs),
        provider_config=dict(request.provider_config),
        context=context,
    )
    return ExperimentApiMapper.to_run_response(
        experiment_id=experiment_id,
        runs=runs,
        leaderboard=leaderboard,
    )


@router.get(
    "/{experiment_id}/leaderboard",
    response_model=LeaderboardResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get leaderboard",
    description="Return the latest leaderboard for an experiment.",
)
def get_leaderboard(
    experiment_id: str,
    experiment_api_service: Annotated[
        object,
        Depends(get_experiment_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> LeaderboardResponse:
    """
    Return the latest leaderboard for an experiment.
    """
    return ExperimentApiMapper.to_leaderboard_response(
        experiment_api_service.get_leaderboard(experiment_id, context)
    )
