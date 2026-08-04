from pathlib import Path

import pytest

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.repositories.policy_administration_repository import (
    PolicyAdministrationRepository,
)
from kavach.repositories.sqlite import SQLitePolicyAdministrationRepository
from tests.repositories.contract.test_policy_administration_repository_contract import (
    PolicyAdministrationRepositoryContract,
)


class TestSQLitePolicyAdministrationRepository(
    PolicyAdministrationRepositoryContract,
):
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        database = SQLiteDatabase(tmp_path / "kavach.db")
        database.initialize()
        self._repository = SQLitePolicyAdministrationRepository(database)

    def repository(self) -> PolicyAdministrationRepository:
        return self._repository
