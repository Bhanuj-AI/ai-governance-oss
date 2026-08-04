from __future__ import annotations

from typing import final

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.domain.experiments import ExperimentCandidate
from kavach.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from kavach.repositories.mappers.experiment_candidate_persistence_mapper import (
    ExperimentCandidatePersistenceMapper,
)


@final
class SQLiteExperimentCandidateRepository(
    ExperimentCandidateRepository
):
    """
    SQLite implementation of the ExperimentCandidateRepository contract.
    """

    _INSERT_CANDIDATE_SQL = """
    INSERT OR REPLACE INTO experiment_candidate (
        candidate_id,
        experiment_id,
        name,
        prompt_id,
        prompt_version,
        model_id,
        model_version,
        dataset_id,
        dataset_version,
        evaluation_provider,
        temperature,
        top_p,
        max_tokens,
        metadata_json,
        created_at
    )
    VALUES (
        :candidate_id,
        :experiment_id,
        :name,
        :prompt_id,
        :prompt_version,
        :model_id,
        :model_version,
        :dataset_id,
        :dataset_version,
        :evaluation_provider,
        :temperature,
        :top_p,
        :max_tokens,
        :metadata_json,
        :created_at
    )
    """

    _SELECT_CANDIDATE_COLUMNS = """
    SELECT
        candidate_id,
        experiment_id,
        name,
        prompt_id,
        prompt_version,
        model_id,
        model_version,
        dataset_id,
        dataset_version,
        evaluation_provider,
        temperature,
        top_p,
        max_tokens,
        metadata_json,
        created_at
    FROM experiment_candidate
    """

    def __init__(
        self,
        database: SQLiteDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        candidate: ExperimentCandidate,
    ) -> None:
        record = ExperimentCandidatePersistenceMapper.to_persistence_record(
            candidate
        )

        with self._database.connect() as connection:
            try:
                connection.execute(
                    self._INSERT_CANDIDATE_SQL,
                    record,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        candidate_id: str,
    ) -> ExperimentCandidate | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_CANDIDATE_COLUMNS} WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()

        if row is None:
            return None

        return ExperimentCandidatePersistenceMapper.from_persistence_record(
            row
        )

    def find_by_experiment_id(
        self,
        experiment_id: str,
    ) -> list[ExperimentCandidate]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_CANDIDATE_COLUMNS} "
                "WHERE experiment_id = ? "
                "ORDER BY created_at, name",
                (experiment_id,),
            ).fetchall()

        return ExperimentCandidatePersistenceMapper.from_persistence_records(
            rows
        )

    def find_all(self) -> list[ExperimentCandidate]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_CANDIDATE_COLUMNS} "
                "ORDER BY experiment_id, created_at, name"
            ).fetchall()

        return ExperimentCandidatePersistenceMapper.from_persistence_records(
            rows
        )
