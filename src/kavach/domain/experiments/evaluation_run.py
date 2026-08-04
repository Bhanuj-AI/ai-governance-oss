from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from kavach.domain.experiments.experiment_candidate import ExperimentCandidate


class EvaluationRunStatus(str, Enum):
    """
    Lifecycle state for an experiment evaluation run.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


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
            EvaluationRunStatus.FAILED,
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
