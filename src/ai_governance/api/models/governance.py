from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class EvaluationComparisonRequest(BaseModel):
    """
    REST request body for comparing two evaluations.
    """

    baseline_evaluation_id: str = Field(min_length=1)
    candidate_evaluation_id: str = Field(min_length=1)

    @field_validator("baseline_evaluation_id", "candidate_evaluation_id")
    @classmethod
    def evaluation_id_must_not_be_blank(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError("Evaluation ID must not be blank.")
        return value


class EvaluationMetricComparisonResponse(BaseModel):
    """
    REST representation of one metric comparison.
    """

    metric_name: str
    baseline_value: float | None = None
    candidate_value: float | None = None
    score_difference: float | None = None


class EvaluationComparisonResponse(BaseModel):
    """
    REST representation of an evaluation comparison.
    """

    execution_id: str
    baseline_evaluation_id: str
    candidate_evaluation_id: str
    metric_comparisons: list[EvaluationMetricComparisonResponse]


class DriftAnalysisRequest(BaseModel):
    """
    REST request body for evaluating drift between two evaluations.
    """

    baseline_evaluation_id: str = Field(min_length=1)
    candidate_evaluation_id: str = Field(min_length=1)

    @field_validator("baseline_evaluation_id", "candidate_evaluation_id")
    @classmethod
    def evaluation_id_must_not_be_blank(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError("Evaluation ID must not be blank.")
        return value


class DriftAnalysisResponse(BaseModel):
    """
    REST representation of governance drift analysis.
    """

    baseline_evaluation_id: str
    candidate_evaluation_id: str
    score_difference: float | None = None
    changed_metrics: list[EvaluationMetricComparisonResponse]
    new_metrics: list[EvaluationMetricComparisonResponse]
    removed_metrics: list[EvaluationMetricComparisonResponse]
    severity: str


class GovernanceReportResponse(BaseModel):
    """
    REST representation of a governance report.
    """

    evaluation_id: str
    report: dict[str, Any] = Field(default_factory=dict)
