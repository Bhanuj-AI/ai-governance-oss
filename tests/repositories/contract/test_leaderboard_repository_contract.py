from abc import ABC, abstractmethod
from datetime import UTC, datetime

from kavach.domain.experiments import (
    Leaderboard,
    LeaderboardEntry,
)
from kavach.repositories.leaderboard_repository import (
    LeaderboardRepository,
)


class LeaderboardRepositoryContract(ABC):
    """
    Behavioral contract every LeaderboardRepository implementation must satisfy.
    """

    @abstractmethod
    def repository(self) -> LeaderboardRepository:
        """
        Return a fresh leaderboard repository instance.
        """

    def create_leaderboard(self) -> Leaderboard:
        return Leaderboard(
            leaderboard_id="leaderboard-1",
            experiment_id="experiment-1",
            ranking_strategy="overall_score",
            generated_at=datetime(2026, 6, 26, tzinfo=UTC),
            entries=(
                LeaderboardEntry(
                    rank=1,
                    candidate_id="candidate-1",
                    overall_score=0.94,
                    metrics={"GROUNDEDNESS": 0.95},
                    cost=0.02,
                    latency=0.4,
                    reason="Top candidate.",
                ),
                LeaderboardEntry(
                    rank=2,
                    candidate_id="candidate-2",
                    overall_score=0.88,
                    metrics={"GROUNDEDNESS": 0.89},
                    cost=0.03,
                    latency=0.5,
                    reason="Second candidate.",
                ),
            ),
        )

    def test_should_save_and_load_leaderboard(self) -> None:
        repository = self.repository()
        expected = self.create_leaderboard()

        repository.save(expected)

        assert repository.find_by_id(expected.leaderboard_id) == expected

    def test_should_find_leaderboards_by_experiment_id(self) -> None:
        repository = self.repository()
        expected = self.create_leaderboard()

        repository.save(expected)

        assert repository.find_by_experiment_id(expected.experiment_id) == [
            expected
        ]
        assert repository.find_by_experiment_id("missing") == []

    def test_should_replace_leaderboard_with_same_id(self) -> None:
        repository = self.repository()
        expected = self.create_leaderboard()
        replacement = Leaderboard(
            leaderboard_id=expected.leaderboard_id,
            experiment_id=expected.experiment_id,
            ranking_strategy="lowest_cost",
            generated_at=expected.generated_at,
            entries=(
                LeaderboardEntry(
                    rank=1,
                    candidate_id="candidate-2",
                    overall_score=-0.02,
                    metrics={"HALLUCINATION": 0.1},
                    cost=0.02,
                    latency=0.5,
                    reason="Ranked by lowest model cost.",
                ),
            ),
        )

        repository.save(expected)
        repository.save(replacement)

        assert repository.find_by_id(expected.leaderboard_id) == replacement

    def test_should_find_all_leaderboards(self) -> None:
        repository = self.repository()
        expected = self.create_leaderboard()

        repository.save(expected)

        assert repository.find_all() == [expected]
