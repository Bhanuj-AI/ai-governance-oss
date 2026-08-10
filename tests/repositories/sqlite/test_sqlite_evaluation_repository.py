from pathlib import Path

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.repositories.evaluation_repository import (
    EvaluationRepository,
)
from ai_governance.repositories.sqlite.sqlite_evaluation_repository import (
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

        database = SQLiteDatabase(tmp_path / "ai_governance.db")

        database.initialize()

        self._repository = SQLiteEvaluationRepository(database)

    def repository(self) -> EvaluationRepository:
        return self._repository
