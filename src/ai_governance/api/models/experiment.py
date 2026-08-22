from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from ai_governance.api.models.evaluation import (
    EvaluationMetricResponse,
    EvaluationMetricSpecRequest,
)
from ai_governance.api.models.governance import EvaluationMetricComparisonResponse


class ExperimentCreateRequest(BaseModel):
    """
    REST request body for creating an experiment.
    """

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "description")
    @classmethod
    def required_string_must_not_be_blank(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value


class ExperimentResponse(BaseModel):
    """
    REST representation of an experiment.
    """

    experiment_id: str
    name: str
    description: str
    owner: str
    status: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentCandidateCreateRequest(BaseModel):
    """
    REST request body for registering an experiment candidate.
    """

    candidate_name: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    provider_name: str | None = None
    provider_installation_id: str | None = None
    runtime_connection_id: str | None = None
    runtime_parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "candidate_name",
        "prompt_version",
        "model_version",
        "dataset_version",
    )
    @classmethod
    def required_reference_must_not_be_blank(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value

    @model_validator(mode="after")
    def provider_reference_is_required(self) -> ExperimentCandidateCreateRequest:
        if not (self.provider_name or "").strip() and not (self.provider_installation_id or "").strip():
            raise ValueError("provider_name or provider_installation_id is required.")
        return self


class ExperimentCandidateResponse(BaseModel):
    """
    REST representation of an experiment candidate.
    """

    candidate_id: str
    experiment_id: str
    candidate_name: str
    prompt_id: str
    prompt_version: str
    model_id: str
    model_version: str
    dataset_id: str
    dataset_version: str
    provider_name: str
    provider_installation_id: str | None = None
    runtime_connection_id: str | None = None
    runtime_parameters: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ExperimentCandidateComparisonResponse(BaseModel):
    """
    REST representation of a candidate-to-candidate comparison.

    Candidate configuration is returned in full so the client can render a
    field-by-field comparison without reconstructing references locally.
    """

    experiment_id: str
    baseline_candidate: ExperimentCandidateResponse
    comparison_candidate: ExperimentCandidateResponse
    metric_comparisons: list[EvaluationMetricComparisonResponse] = Field(
        default_factory=list
    )


class ExperimentRunRequest(BaseModel):
    """
    REST request body for synchronous experiment execution.
    """

    metric_specs: list[EvaluationMetricSpecRequest] = Field(default_factory=list)
    provider_config: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    idempotency_key: str | None = None
    requested_by: str | None = None
    actor_type: str | None = None
    reason: str | None = None
    dry_run: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    submitted_by: str | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)

    @property
    def is_async_submission(self) -> bool:
        return self.idempotency_key is not None


class EvaluationRunResponse(BaseModel):
    """
    REST representation of one experiment evaluation run.
    """

    run_id: str
    experiment_id: str
    candidate_id: str
    dataset_version: str
    provider_name: str
    evaluation_result_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str
    failure_reason: str | None = None
    total_item_count: int | None = Field(default=None, ge=0)
    completed_item_count: int = Field(default=0, ge=0)
    evaluated_item_count: int = Field(default=0, ge=0)


class EvaluationRunItemResultResponse(BaseModel):
    """Safe, item-level evaluator evidence displayed for one experiment run."""

    evaluation_id: str
    execution_id: str
    evaluator_type: str
    evaluator_version: str
    created_at: datetime
    model_latency_ms: int | None = Field(default=None, ge=0)
    metrics: list[EvaluationMetricResponse] = Field(default_factory=list)


class EvaluationRunResultPageResponse(BaseModel):
    """Bounded page of complete item evaluations, including partial runs."""

    run_id: str
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0)
    items: list[EvaluationRunItemResultResponse] = Field(default_factory=list)


class ExperimentRunProgressResponse(BaseModel):
    """Live, persisted progress for the active candidate evaluation run."""

    run_id: str
    candidate_id: str
    candidate_name: str
    candidate_position: int = Field(ge=1)
    total_item_count: int | None = Field(default=None, ge=0)
    completed_item_count: int = Field(ge=0)
    evaluated_item_count: int = Field(ge=0)


class ExperimentRunPlanResponse(BaseModel):
    """Preflight execution volume and active-run progress."""

    experiment_id: str
    candidate_count: int = Field(ge=0)
    dataset_item_count: int = Field(ge=0)
    model_invocation_count: int = Field(ge=0)
    evaluation_item_count: int = Field(ge=0)
    active_run: ExperimentRunProgressResponse | None = None


class LeaderboardEntryResponse(BaseModel):
    """
    REST representation of one leaderboard entry.
    """

    rank: int
    candidate_id: str
    overall_score: float
    metrics: dict[str, float]
    cost: float | None = None
    latency: float | None = None
    reason: str


class LeaderboardResponse(BaseModel):
    """
    REST representation of an experiment leaderboard.
    """

    leaderboard_id: str
    experiment_id: str
    ranking_strategy: str
    generated_at: datetime
    entries: list[LeaderboardEntryResponse]


class ExperimentRunResponse(BaseModel):
    """
    REST response body for synchronous experiment execution.
    """

    experiment_id: str
    runs: list[EvaluationRunResponse]
    leaderboard: LeaderboardResponse | None = None
