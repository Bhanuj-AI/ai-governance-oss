from __future__ import annotations

from typing import final

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.domain.experiments import EvaluationRun
from kavach.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from kavach.repositories.mappers.evaluation_run_persistence_mapper import (
    EvaluationRunPersistenceMapper,
)


@final
class SQLiteEvaluationRunRepository(EvaluationRunRepository):
    """
    SQLite implementation of the EvaluationRunRepository contract.
    """

    _INSERT_RUN_SQL = """
    INSERT OR REPLACE INTO evaluation_run (
        run_id,
        experiment_id,
        candidate_id,
        dataset_version,
        evaluation_provider,
        evaluation_result_id,
        started_at,
        completed_at,
        status
    )
    VALUES (
        :run_id,
        :experiment_id,
        :candidate_id,
        :dataset_version,
        :evaluation_provider,
        :evaluation_result_id,
        :started_at,
        :completed_at,
        :status
    )
    """

    _SELECT_RUN_COLUMNS = """
    SELECT
        run_id,
        experiment_id,
        candidate_id,
        dataset_version,
        evaluation_provider,
        evaluation_result_id,
        started_at,
        completed_at,
        status
    FROM evaluation_run
    """

    def __init__(
        self,
        database: SQLiteDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        run: EvaluationRun,
    ) -> None:
        record = EvaluationRunPersistenceMapper.to_persistence_record(run)

        with self._database.connect() as connection:
            try:
                connection.execute(
                    self._INSERT_RUN_SQL,
                    record,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        run_id: str,
    ) -> EvaluationRun | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_RUN_COLUMNS} WHERE run_id = ?",
                (run_id,),
            ).fetchone()

        if row is None:
            return None

        return EvaluationRunPersistenceMapper.from_persistence_record(row)

    def find_by_experiment_id(
        self,
        experiment_id: str,
    ) -> list[EvaluationRun]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_RUN_COLUMNS} "
                "WHERE experiment_id = ? "
                "ORDER BY started_at, run_id",
                (experiment_id,),
            ).fetchall()

        return EvaluationRunPersistenceMapper.from_persistence_records(rows)

    def find_by_candidate_id(
        self,
        candidate_id: str,
    ) -> list[EvaluationRun]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_RUN_COLUMNS} "
                "WHERE candidate_id = ? "
                "ORDER BY started_at, run_id",
                (candidate_id,),
            ).fetchall()

        return EvaluationRunPersistenceMapper.from_persistence_records(rows)

    def find_all(self) -> list[EvaluationRun]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_RUN_COLUMNS} "
                "ORDER BY experiment_id, candidate_id, started_at, run_id"
            ).fetchall()

        return EvaluationRunPersistenceMapper.from_persistence_records(rows)
