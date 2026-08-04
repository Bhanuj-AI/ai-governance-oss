from pathlib import Path

import pytest

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.repositories.dataset_repository import DatasetRepository
from kavach.repositories.sqlite.sqlite_dataset_repository import (
    SQLiteDatasetRepository,
)
from tests.repositories.contract.test_dataset_repository_contract import (
    DatasetRepositoryContract,
)


class TestSQLiteDatasetRepository(DatasetRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        tmp_path: Path,
    ) -> None:
        database = SQLiteDatabase(tmp_path / "kavach.db")
        database.initialize()

        self._repository = SQLiteDatasetRepository(database)

    def repository(self) -> DatasetRepository:
        return self._repository
