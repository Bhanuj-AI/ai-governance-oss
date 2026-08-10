from __future__ import annotations

from ai_governance.domain.experiments import Leaderboard
from ai_governance.repositories.leaderboard_repository import LeaderboardRepository


class InMemoryLeaderboardRepository(LeaderboardRepository):
    """
    In-memory LeaderboardRepository used by tests and local workflows.
    """

    def __init__(self) -> None:
        self._leaderboards_by_id: dict[str, Leaderboard] = {}

    def save(
        self,
        leaderboard: Leaderboard,
    ) -> None:
        self._leaderboards_by_id[leaderboard.leaderboard_id] = leaderboard

    def find_by_id(
        self,
        leaderboard_id: str,
    ) -> Leaderboard | None:
        return self._leaderboards_by_id.get(leaderboard_id)

    def find_by_experiment_id(
        self,
        experiment_id: str,
    ) -> list[Leaderboard]:
        return [
            leaderboard
            for leaderboard in self._leaderboards_by_id.values()
            if leaderboard.experiment_id == experiment_id
        ]

    def find_all(self) -> list[Leaderboard]:
        return list(self._leaderboards_by_id.values())
