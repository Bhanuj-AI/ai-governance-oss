from pathlib import Path

import pytest

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from kavach.repositories.sqlite.sqlite_evaluation_run_repository import (
    SQLiteEvaluationRunRepository,
)
from tests.repositories.contract.test_evaluation_run_repository_contract import (
    EvaluationRunRepositoryContract,
)


class TestSQLiteEvaluationRunRepository(
    EvaluationRunRepositoryContract
):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        tmp_path: Path,
    ) -> None:
        database = SQLiteDatabase(tmp_path / "kavach.db")
        database.initialize()

        self._repository = SQLiteEvaluationRunRepository(database)

    def repository(self) -> EvaluationRunRepository:
        return self._repository
