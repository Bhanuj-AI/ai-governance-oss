from pathlib import Path

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.repositories.dataset_repository import DatasetRepository
from ai_governance.repositories.sqlite.sqlite_dataset_repository import (
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
        database = SQLiteDatabase(tmp_path / "ai_governance.db")
        database.initialize()

        self._repository = SQLiteDatasetRepository(database)

    def repository(self) -> DatasetRepository:
        return self._repository
