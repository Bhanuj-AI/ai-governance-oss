from pathlib import Path

import pytest

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.repositories.evaluation_repository import (
    EvaluationRepository,
)
from kavach.repositories.sqlite.sqlite_evaluation_repository import (
    SQLiteEvaluationRepository,
)
from tests.repositories.contract.test_evaluation_repository_contract import (
    EvaluationRepositoryContract,
)


class TestSQLiteEvaluationRepository(
    EvaluationRepositoryContract,
):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        tmp_path: Path,
    ) -> None:

        database = SQLiteDatabase(tmp_path / "kavach.db")

        database.initialize()

        self._repository = SQLiteEvaluationRepository(database)

    def repository(self) -> EvaluationRepository:
        return self._repository
