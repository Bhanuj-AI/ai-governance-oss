from pathlib import Path

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.repositories.leaderboard_repository import (
    LeaderboardRepository,
)
from ai_governance.repositories.sqlite.sqlite_leaderboard_repository import (
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
        database = SQLiteDatabase(tmp_path / "ai_governance.db")
        database.initialize()

        self._repository = SQLiteLeaderboardRepository(database)

    def repository(self) -> LeaderboardRepository:
        return self._repository
