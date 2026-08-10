from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_governance.api.models.evaluation import (
    EvaluationArtifactResponse,
    EvaluationHistoryResponse,
    EvaluationJobSubmitRequest,
    EvaluationMetricResponse,
    EvaluationMetricSpecRequest,
    EvaluationResponse,
    EvaluationSubmitRequest,
)
from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.domain.jobs import JobSubmission, JobType
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation.evaluation_metrics import EvaluationMetricSpec
from ai_governance.providers.provider_descriptor import scrub_sensitive_metadata


class EvaluationApiMapper:
    """
    Converts between evaluation REST DTOs and application/domain objects.
    """

    @staticmethod
    def to_workflow_execution(
        request: EvaluationSubmitRequest,
    ) -> WorkflowExecution:
        """
        Convert a submit request into the canonical workflow execution model.
        """
        return WorkflowExecution(
            workflow_id=request.workflow_id,
            execution_id=request.execution_id,
            workflow_name=request.workflow_name or request.workflow_id,
            workflow_version=request.workflow_version or "unknown",
            execution_status=request.execution_status,
            input=dict(request.input),
            final_state=dict(request.final_state),
            events=[dict(event) for event in request.events],
        )

    @staticmethod
    def to_metric_specs(
        metric_specs: Sequence[EvaluationMetricSpecRequest],
    ) -> list[EvaluationMetricSpec]:
        """
        Convert requested REST metric specs into evaluation metric specs.
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
    def to_response(
        result: EvaluationResult,
    ) -> EvaluationResponse:
        """
        Convert an EvaluationResult into a REST response DTO.
        """
        return EvaluationResponse(
            evaluation_id=result.evaluation_id,
            execution_id=result.execution_id,
            provider_name=result.provider_name,
            provider_version=result.provider_version,
            metrics=[
                EvaluationMetricResponse(
                    name=metric.metric_name,
                    score=metric.metric_value,
                    explanation=metric.explanation,
                )
                for metric in result.metrics
            ],
            artifacts=[
                EvaluationArtifactResponse(
                    artifact_type=artifact.artifact_type,
                    uri=artifact.uri,
                    payload=(
                        dict(artifact.payload) if artifact.payload is not None else None
                    ),
                    metadata=dict(artifact.metadata),
                )
                for artifact in result.artifacts
            ],
            provider_metadata=_scrub_mapping(result.provider_metadata),
            provider_descriptor_snapshot=(
                _scrub_mapping(result.provider_descriptor_snapshot)
                if result.provider_descriptor_snapshot is not None
                else None
            ),
            created_at=result.created_at,
        )

    @staticmethod
    def to_history_response(
        execution_id: str,
        results: Sequence[EvaluationResult],
    ) -> EvaluationHistoryResponse:
        """
        Convert persisted evaluation results into a history response.
        """
        return EvaluationHistoryResponse(
            execution_id=execution_id,
            evaluations=[EvaluationApiMapper.to_response(result) for result in results],
        )

    @staticmethod
    def to_job_submission(
        request: EvaluationJobSubmitRequest,
    ) -> JobSubmission:
        """
        Convert an async evaluation request into a job submission.
        """
        return JobSubmission(
            job_type=JobType.EVALUATION,
            input_refs={
                "operation": "evaluation.submit_async",
                "request_id": request.request_id,
                "correlation_id": (request.correlation_id or request.request_id),
                "provider_name": request.provider_name,
                "provider_installation_id": request.provider_installation_id,
                "workflow_id": request.workflow_id,
                "execution_id": request.execution_id,
                "workflow_name": request.workflow_name,
                "workflow_version": request.workflow_version,
                "execution_status": request.execution_status,
                "input": dict(request.input),
                "final_state": dict(request.final_state),
                "events": [dict(event) for event in request.events],
                "metric_specs": [
                    metric.model_dump(mode="json") for metric in request.metric_specs
                ],
                "provider_config": dict(request.provider_config),
                "metadata": dict(request.metadata),
                "requested_by": request.requested_by,
                "actor_type": request.actor_type,
                "reason": request.reason,
            },
            idempotency_key=request.idempotency_key,
            submitted_by=request.submitted_by,
            max_attempts=request.max_attempts,
        )


def _scrub_mapping(
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return scrub_sensitive_metadata(dict(metadata))
