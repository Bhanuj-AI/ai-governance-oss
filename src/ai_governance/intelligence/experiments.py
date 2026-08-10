"""OSS Experiment Advisor backed by deterministic candidate rankings."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from ai_governance.spi.intelligence import (
    AdvisorDescriptor,
    AdvisorEvidence,
    AdvisorFinding,
    AdvisorRequest,
    FindingSeverity,
)


class CandidateRankingSource(Protocol):
    """Read-only source for completed, deterministic experiment rankings."""

    def rank_candidates(self, experiment_id: str) -> Sequence[object]:
        """Return candidates ranked from the completed evaluation evidence."""
        ...


class ExperimentAdvisor:
    """Recommend the top experiment candidate from existing evaluation results.

    The advisor receives a narrow ranking source rather than repositories or
    execution services. It cannot start an evaluation or mutate an experiment.
    """

    descriptor = AdvisorDescriptor(
        advisor_id="experiments",
        version="1",
        title="Experiment Advisor",
        capabilities=("candidate-comparison", "candidate-ranking", "winner-recommendation"),
        required_context=("experiment_id",),
    )

    def __init__(self, ranking_source_factory: Callable[[], CandidateRankingSource]) -> None:
        self._ranking_source_factory = ranking_source_factory

    def analyze(self, request: AdvisorRequest) -> AdvisorFinding:
        """Return only completed-evaluation ranking evidence for one experiment."""
        experiment_id = str(request.context["experiment_id"])
        rankings = tuple(self._ranking_source_factory().rank_candidates(experiment_id))
        if not rankings:
            return AdvisorFinding(
                advisor_id=self.descriptor.advisor_id,
                advisor_version=self.descriptor.version,
                severity=FindingSeverity.INFO,
                summary="No completed candidate rankings are available for this experiment.",
            )

        winner = rankings[0]
        evidence = tuple(_ranking_evidence(ranking) for ranking in rankings)
        return AdvisorFinding(
            advisor_id=self.descriptor.advisor_id,
            advisor_version=self.descriptor.version,
            severity=FindingSeverity.INFO,
            summary=(
                f"Candidate '{winner.candidate.candidate_id}' is the deterministic "
                f"recommendation from {len(rankings)} completed evaluation rankings."
            ),
            findings=evidence,
            metadata={
                "experiment_id": experiment_id,
                "recommended_candidate_id": winner.candidate.candidate_id,
                "ranking_strategy": winner.ranking_strategy,
            },
        )


def _ranking_evidence(ranking: object) -> AdvisorEvidence:
    """Map the stable CandidateRanking domain shape to advisor evidence."""
    candidate = ranking.candidate
    return AdvisorEvidence(
        evidence_id=f"experiment-ranking:{ranking.experiment_id}:{candidate.candidate_id}",
        kind="candidate-ranking",
        summary=(
            f"Candidate '{candidate.candidate_id}' is ranked #{ranking.rank} "
            f"with an overall score of {ranking.overall_score}."
        ),
        attributes={
            "experiment_id": ranking.experiment_id,
            "candidate_id": candidate.candidate_id,
            "candidate_name": candidate.name,
            "rank": ranking.rank,
            "overall_score": ranking.overall_score,
            "ranking_strategy": ranking.ranking_strategy,
            "reason": ranking.reason,
            "evaluation_run_id": ranking.evaluation_run_id,
            "evaluation_result_id": ranking.evaluation_result_id,
        },
    )


__all__ = ["CandidateRankingSource", "ExperimentAdvisor"]
