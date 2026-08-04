from pathlib import Path

import pytest

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from kavach.repositories.sqlite.sqlite_experiment_candidate_repository import (
    SQLiteExperimentCandidateRepository,
)
from tests.repositories.contract.test_experiment_candidate_repository_contract import (
    ExperimentCandidateRepositoryContract,
)


class TestSQLiteExperimentCandidateRepository(
    ExperimentCandidateRepositoryContract
):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        tmp_path: Path,
    ) -> None:
        database = SQLiteDatabase(tmp_path / "kavach.db")
        database.initialize()

        self._repository = SQLiteExperimentCandidateRepository(database)

    def repository(self) -> ExperimentCandidateRepository:
        return self._repository
