from pathlib import Path

import pytest

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.repositories.experiment_repository import ExperimentRepository
from kavach.repositories.sqlite.sqlite_experiment_repository import (
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
        database = SQLiteDatabase(tmp_path / "kavach.db")
        database.initialize()

        self._repository = SQLiteExperimentRepository(database)

    def repository(self) -> ExperimentRepository:
        return self._repository
