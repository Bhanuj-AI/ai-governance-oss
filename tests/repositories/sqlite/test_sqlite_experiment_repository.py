from pathlib import Path

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.repositories.experiment_repository import ExperimentRepository
from ai_governance.repositories.sqlite.sqlite_experiment_repository import (
    SQLiteExperimentRepository,
)
from tests.repositories.contract.test_experiment_repository_contract import (
    ExperimentRepositoryContract,
)


class TestSQLiteExperimentRepository(ExperimentRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        tmp_path: Path,
    ) -> None:
        database = SQLiteDatabase(tmp_path / "ai_governance.db")
        database.initialize()

        self._repository = SQLiteExperimentRepository(database)

    def repository(self) -> ExperimentRepository:
        return self._repository
