from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ai_governance.domain.history import EvaluationMetricComparison


@dataclass(frozen=True)
class ExperimentCandidate:
    """
    Immutable AI configuration participating in an experiment.

    A candidate binds together the exact prompt, model, dataset, evaluation
    provider, and runtime parameters that should be replayable for historical
    investigation and governance decisions.
    """

    candidate_id: str
    experiment_id: str
    name: str
    prompt_id: str
    prompt_version: str
    model_id: str
    model_version: str
    dataset_id: str
    dataset_version: str
    evaluation_provider: str
    temperature: float
    top_p: float
    max_tokens: int
    metadata: dict[str, Any]
    created_at: datetime

    def __post_init__(self) -> None:
        self._require_non_empty("candidate_id", self.candidate_id)
        self._require_non_empty("experiment_id", self.experiment_id)
        self._require_non_empty("name", self.name)
        self._require_non_empty("prompt_id", self.prompt_id)
        self._require_non_empty("prompt_version", self.prompt_version)
        self._require_non_empty("model_id", self.model_id)
        self._require_non_empty("model_version", self.model_version)
        self._require_non_empty("dataset_id", self.dataset_id)
        self._require_non_empty("dataset_version", self.dataset_version)
        self._require_non_empty(
            "evaluation_provider",
            self.evaluation_provider,
        )

        if self.temperature < 0:
            raise ValueError(
                "Experiment candidate temperature must not be negative."
            )

        if not 0 < self.top_p <= 1:
            raise ValueError(
                "Experiment candidate top_p must be between 0 and 1."
            )

        if self.max_tokens <= 0:
            raise ValueError(
                "Experiment candidate max_tokens must be greater than zero."
            )

        object.__setattr__(self, "metadata", dict(self.metadata))

    @staticmethod
    def _require_non_empty(
        field_name: str,
        value: str,
    ) -> None:
        if not value.strip():
            raise ValueError(
                f"Experiment candidate {field_name} must not be empty."
            )


@dataclass(frozen=True)
class CandidateComparison:
    """
    Configuration-level comparison between two experiment candidates.

    This reveals what changed in the governed AI configuration before teams
    interpret evaluation quality changes.
    """

    baseline_candidate_id: str
    candidate_candidate_id: str
    experiment_id: str | None = None
    baseline_candidate: ExperimentCandidate | None = None
    candidate: ExperimentCandidate | None = None
    winner: ExperimentCandidate | None = None
    metric_comparisons: list[EvaluationMetricComparison] = field(
        default_factory=list
    )
    overall_score: float | None = None
    baseline_overall_score: float | None = None
    candidate_overall_score: float | None = None
    cost_delta: float | None = None
    latency_delta: float | None = None
    reason: str | None = None
    prompt_id_changed: bool = False
    prompt_version_changed: bool = False
    model_id_changed: bool = False
    model_version_changed: bool = False
    dataset_id_changed: bool = False
    dataset_version_changed: bool = False
    evaluation_provider_changed: bool = False
    temperature_changed: bool = False
    top_p_changed: bool = False
    max_tokens_changed: bool = False
    metadata_changed: bool = False

    @property
    def has_changes(self) -> bool:
        """
        Return whether any candidate configuration changed.
        """

        return any(
            [
                self.prompt_id_changed,
                self.prompt_version_changed,
                self.model_id_changed,
                self.model_version_changed,
                self.dataset_id_changed,
                self.dataset_version_changed,
                self.evaluation_provider_changed,
                self.temperature_changed,
                self.top_p_changed,
                self.max_tokens_changed,
                self.metadata_changed,
                bool(self.metric_comparisons),
            ]
        )

    @property
    def score_difference(self) -> float | None:
        """
        Return candidate-minus-baseline score when both are available.
        """

        if (
            self.baseline_overall_score is None
            or self.candidate_overall_score is None
        ):
            return None

        return self.candidate_overall_score - self.baseline_overall_score
