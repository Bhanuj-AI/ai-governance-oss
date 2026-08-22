from __future__ import annotations

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, status

from ai_governance.api.dependencies import (
    get_drift_explanation_service,
    get_evaluation_api_service,
    get_job_api_service,
)
from ai_governance.api.dependencies.provider_installations import (
    get_provider_installation_service,
)
from ai_governance.api.dependencies.settings_control import get_configuration_service
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.mappers import (
    EvaluationApiMapper,
    GovernanceInsightApiMapper,
    JobApiMapper,
)
from ai_governance.api.models import (
    ErrorResponse,
    EvaluationHistoryResponse,
    EvaluationJobSubmitRequest,
    EvaluationResponse,
    EvaluationSubmitRequest,
    GovernanceInsightResponse,
    JobResponse,
)
from ai_governance.domain.jobs import JobExecutionContext
from ai_governance.settings_control.operational import setting_context

router = APIRouter(
    prefix="/api/v1/evaluations",
    tags=["Evaluations"],
)


@router.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Requested evaluation job was invalid.",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Idempotency key conflicts with a different input.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="Submit evaluation job",
    description="Queue an asynchronous evaluation job.",
)
def submit_evaluation_job(
    request: EvaluationJobSubmitRequest,
    job_api_service: Annotated[
        object,
        Depends(get_job_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
    configuration_service=Depends(get_configuration_service),
    provider_installation_service=Depends(get_provider_installation_service),
) -> JobResponse:
    """
    Queue an asynchronous evaluation job.
    """
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
    provider_name = request.provider_name
    if request.provider_installation_id:
        provider_name = provider_installation_service.resolve_provider_type(
            request.provider_installation_id, context
        ).provider_type
    elif provider_name is None:
        provider_name = str(
            configuration_service.get(
                "evaluation.default_provider", setting_context(context)
            )
        )
    request = request.model_copy(update={"provider_name": provider_name})
    submission = EvaluationApiMapper.to_job_submission(request)
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


@router.post(
    "",
    response_model=EvaluationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Requested metric is not supported.",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Provider was not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="Submit evaluation",
    description="Execute and persist a synchronous evaluation.",
)
def submit_evaluation(
    request: EvaluationSubmitRequest,
    evaluation_api_service: Annotated[
        object,
        Depends(get_evaluation_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
    configuration_service=Depends(get_configuration_service),
) -> EvaluationResponse:
    """
    Execute and persist a synchronous evaluation request.
    """
    result = evaluation_api_service.submit_evaluation(
        execution=EvaluationApiMapper.to_workflow_execution(request),
        provider_name=(
            request.provider_name
            or (
                None
                if request.provider_installation_id
                else str(
                    configuration_service.get(
                        "evaluation.default_provider", setting_context(context)
                    )
                )
            )
        ),
        metric_specs=EvaluationApiMapper.to_metric_specs(request.metric_specs),
        provider_config=dict(request.provider_config),
        provider_installation_id=request.provider_installation_id,
        context=context,
    )
    return EvaluationApiMapper.to_response(result)


@router.get(
    "/history/{execution_id}",
    response_model=EvaluationHistoryResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="Get evaluation history",
    description="Return persisted evaluations for an execution.",
)
def get_evaluation_history(
    execution_id: str,
    evaluation_api_service: Annotated[
        object,
        Depends(get_evaluation_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> EvaluationHistoryResponse:
    """
    Return all persisted evaluations for an execution ID.
    """
    return EvaluationApiMapper.to_history_response(
        execution_id=execution_id,
        results=evaluation_api_service.get_history(execution_id, context),
    )


@router.get(
    "/latest/{execution_id}",
    response_model=EvaluationResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Evaluation was not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="Get latest evaluation",
    description="Return the latest persisted evaluation for an execution.",
)
def get_latest_evaluation(
    execution_id: str,
    evaluation_api_service: Annotated[
        object,
        Depends(get_evaluation_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> EvaluationResponse:
    """
    Return the newest evaluation result for an execution ID.
    """
    return EvaluationApiMapper.to_response(
        evaluation_api_service.get_latest(execution_id, context)
    )


@router.get(
    "/{evaluation_id}",
    response_model=EvaluationResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Evaluation was not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="Get evaluation",
    description="Return a persisted evaluation result by ID.",
)
def get_evaluation(
    evaluation_id: str,
    evaluation_api_service: Annotated[
        object,
        Depends(get_evaluation_api_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> EvaluationResponse:
    """
    Return a persisted evaluation result by evaluation ID.
    """
    return EvaluationApiMapper.to_response(
        evaluation_api_service.get_evaluation(evaluation_id, context)
    )


@router.get(
    "/{evaluation_id}/drift-explanation",
    response_model=GovernanceInsightResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Evaluation was not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="Explain evaluation drift",
    description="Explain drift for an evaluation relative to its prior execution evidence.",
)
def get_evaluation_drift_explanation(
    evaluation_id: str,
    drift_explanation_service: Annotated[
        object,
        Depends(get_drift_explanation_service),
    ],
) -> GovernanceInsightResponse:
    """
    Return a drift explanation for one evaluation when prior evidence exists.
    """
    return GovernanceInsightApiMapper.to_insight_response(
        drift_explanation_service.explain_evaluation(evaluation_id)
    )
