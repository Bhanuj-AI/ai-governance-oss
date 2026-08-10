from pathlib import Path

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from ai_governance.repositories.sqlite.sqlite_evaluation_run_repository import (
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
        database = SQLiteDatabase(tmp_path / "ai_governance.db")
        database.initialize()

        self._repository = SQLiteEvaluationRunRepository(database)

    def repository(self) -> EvaluationRunRepository:
        return self._repository
