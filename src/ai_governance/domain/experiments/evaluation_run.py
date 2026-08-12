from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ai_governance.domain.experiments.experiment_candidate import ExperimentCandidate


class EvaluationRunStatus(str, Enum):
    """
    Lifecycle state for an experiment evaluation run.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class EvaluationRun:
    """
    Immutable record of one candidate evaluation execution.

    Evaluation runs provide the execution evidence that experiment-aware
    comparison and winner selection operate on.
    """

    run_id: str
    experiment_id: str
    candidate_id: str
    dataset_version: str
    evaluation_provider: str
    evaluation_result_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    status: EvaluationRunStatus
    failure_reason: str | None = None
    total_item_count: int | None = None
    completed_item_count: int = 0
    evaluated_item_count: int = 0

    def __post_init__(self) -> None:
        self._require_non_empty("run_id", self.run_id)
        self._require_non_empty("experiment_id", self.experiment_id)
        self._require_non_empty("candidate_id", self.candidate_id)
        self._require_non_empty("dataset_version", self.dataset_version)
        self._require_non_empty(
            "evaluation_provider",
            self.evaluation_provider,
        )

        if self.status == EvaluationRunStatus.RUNNING and self.started_at is None:
            raise ValueError("Running evaluation runs require started_at.")

        if self.status in (
            EvaluationRunStatus.COMPLETED,
            EvaluationRunStatus.EXECUTION_FAILED,
            EvaluationRunStatus.FAILED,
            EvaluationRunStatus.CANCELLED,
        ):
            if self.started_at is None or self.completed_at is None:
                raise ValueError(
                    "Completed and failed evaluation runs require timestamps."
                )

        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError(
                "EvaluationRun completed_at must not be before started_at."
            )

        if self.failure_reason is not None:
            reason = self.failure_reason.strip()
            if not reason:
                raise ValueError("EvaluationRun failure_reason must not be blank.")
            if len(reason) > 500:
                raise ValueError("EvaluationRun failure_reason must be at most 500 characters.")
            object.__setattr__(self, "failure_reason", reason)

        if self.total_item_count is not None and self.total_item_count < 0:
            raise ValueError("EvaluationRun total_item_count must not be negative.")
        if self.completed_item_count < 0:
            raise ValueError("EvaluationRun completed_item_count must not be negative.")
        if self.evaluated_item_count < 0:
            raise ValueError("EvaluationRun evaluated_item_count must not be negative.")
        if (
            self.total_item_count is not None
            and self.completed_item_count > self.total_item_count
        ):
            raise ValueError(
                "EvaluationRun completed_item_count must not exceed total_item_count."
            )
        if self.evaluated_item_count > self.completed_item_count:
            raise ValueError(
                "EvaluationRun evaluated_item_count must not exceed completed_item_count."
            )

        if (
            self.status == EvaluationRunStatus.COMPLETED
            and self.evaluation_result_id is None
        ):
            raise ValueError(
                "Completed evaluation runs require evaluation_result_id."
            )

    @staticmethod
    def _require_non_empty(
        field_name: str,
        value: str,
    ) -> None:
        if not value.strip():
            raise ValueError(
                f"EvaluationRun {field_name} must not be empty."
            )


@dataclass(frozen=True)
class CandidateRanking:
    """
    Deterministic ranking result for one candidate within an experiment.
    """

    experiment_id: str
    candidate: ExperimentCandidate
    evaluation_run_id: str
    evaluation_result_id: str
    overall_score: float
    rank: int
    reason: str = ""
    ranking_strategy: str = "overall_score"

    def __post_init__(self) -> None:
        if self.rank < 0:
            raise ValueError("CandidateRanking rank must not be negative.")

        if not self.evaluation_run_id.strip():
            raise ValueError(
                "CandidateRanking evaluation_run_id must not be empty."
            )

        if not self.evaluation_result_id.strip():
            raise ValueError(
                "CandidateRanking evaluation_result_id must not be empty."
            )
