from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from kavach.api.models.evaluation import EvaluationMetricSpecRequest
from kavach.api.models.governance import EvaluationMetricComparisonResponse


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
    def provider_reference_is_required(self) -> "ExperimentCandidateCreateRequest":
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
