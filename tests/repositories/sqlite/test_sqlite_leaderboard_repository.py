from pathlib import Path

import pytest

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.repositories.leaderboard_repository import (
    LeaderboardRepository,
)
from kavach.repositories.sqlite.sqlite_leaderboard_repository import (
    SQLiteLeaderboardRepository,
)
from tests.repositories.contract.test_leaderboard_repository_contract import (
    LeaderboardRepositoryContract,
)


class TestSQLiteLeaderboardRepository(
    LeaderboardRepositoryContract
):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        tmp_path: Path,
    ) -> None:
        database = SQLiteDatabase(tmp_path / "kavach.db")
        database.initialize()

        self._repository = SQLiteLeaderboardRepository(database)

    def repository(self) -> LeaderboardRepository:
        return self._repository
