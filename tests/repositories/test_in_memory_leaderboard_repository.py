from kavach.repositories.in_memory_leaderboard_repository import (
    InMemoryLeaderboardRepository,
)
from kavach.repositories.leaderboard_repository import (
    LeaderboardRepository,
)
from tests.repositories.contract.test_leaderboard_repository_contract import (
    LeaderboardRepositoryContract,
)


class TestInMemoryLeaderboardRepository(
    LeaderboardRepositoryContract
):
    def repository(self) -> LeaderboardRepository:
        return InMemoryLeaderboardRepository()
