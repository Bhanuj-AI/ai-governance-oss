from __future__ import annotations

from abc import ABC, abstractmethod

from ai_governance.domain.experiments import CandidateRanking


class WinnerSelectionStrategy(ABC):
    """
    Strategy for deterministically selecting the winning candidate.
    """

    @abstractmethod
    def select_winner(
        self,
        rankings: list[CandidateRanking],
    ) -> CandidateRanking:
        pass


class HighestOverallScoreSelectionStrategy(
    WinnerSelectionStrategy
):
    """
    Select the highest-scoring candidate, breaking ties by candidate ID.
    """

    def select_winner(
        self,
        rankings: list[CandidateRanking],
    ) -> CandidateRanking:
        if not rankings:
            raise ValueError("Cannot select a winner from an empty ranking.")

        return max(
            rankings,
            key=lambda ranking: (
                ranking.overall_score,
                ranking.candidate.candidate_id,
            ),
        )
