from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EvaluationMetricSpecRequest(BaseModel):
    """
    REST request shape for a single requested evaluation metric.
    """

    name: str = Field(min_length=1)
    description: str | None = None
    threshold: float | None = None
    weight: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError("Metric name must not be blank.")
        return value


class EvaluationSubmitRequest(BaseModel):
    """
    REST request body for submitting a synchronous evaluation.
    """

    provider_name: str | None = Field(default=None, min_length=1)
    provider_installation_id: str | None = Field(default=None, min_length=1)
    workflow_id: str = Field(min_length=1)
    execution_id: str = Field(min_length=1)
    workflow_name: str | None = None
    workflow_version: str | None = None
    execution_status: str = Field(min_length=1)
    input: dict[str, Any]
    final_state: dict[str, Any]
    events: list[dict[str, Any]] = Field(default_factory=list)
    metric_specs: list[EvaluationMetricSpecRequest] = Field(default_factory=list)
    provider_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "workflow_id",
        "execution_id",
        "execution_status",
    )
    @classmethod
    def required_string_must_not_be_blank(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value


class EvaluationJobSubmitRequest(EvaluationSubmitRequest):
    """
    REST request body for submitting an asynchronous evaluation job.
    """

    request_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    actor_type: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    dry_run: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    submitted_by: str = Field(min_length=1)
    max_attempts: int = Field(default=3, ge=1, le=10)

    @field_validator(
        "request_id",
        "idempotency_key",
        "requested_by",
        "actor_type",
        "reason",
        "submitted_by",
    )
    @classmethod
    def envelope_string_must_not_be_blank(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value


class EvaluationMetricResponse(BaseModel):
    """
    REST response shape for a single evaluation metric score.
    """

    name: str
    score: float
    explanation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationArtifactResponse(BaseModel):
    """
    REST response shape for a provider evaluation artifact.
    """

    artifact_type: str
    uri: str | None = None
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationResponse(BaseModel):
    """
    REST response shape for a persisted evaluation result.
    """

    evaluation_id: str
    execution_id: str
    provider_name: str
    provider_version: str
    metrics: list[EvaluationMetricResponse]
    artifacts: list[EvaluationArtifactResponse] = Field(default_factory=list)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    provider_descriptor_snapshot: dict[str, Any] | None = None
    created_at: datetime | None = None


class EvaluationHistoryResponse(BaseModel):
    """
    REST response shape for all evaluations tied to an execution.
    """

    execution_id: str
    evaluations: list[EvaluationResponse]
