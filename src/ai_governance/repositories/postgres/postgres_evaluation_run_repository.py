from __future__ import annotations

from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.experiments import EvaluationRun
from ai_governance.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from ai_governance.repositories.mappers.evaluation_run_persistence_mapper import (
    EvaluationRunPersistenceMapper,
)


@final
class PostgresEvaluationRunRepository(EvaluationRunRepository):
    """
    PostgreSQL implementation of the EvaluationRunRepository contract.
    """

    _INSERT_RUN_SQL = """
    INSERT INTO evaluation_run (
        run_id,
        experiment_id,
        candidate_id,
        dataset_version,
        evaluation_provider,
        evaluation_result_id,
        started_at,
        completed_at,
        status,
        failure_reason,
        total_item_count,
        completed_item_count,
        evaluated_item_count
    )
    VALUES (
        %(run_id)s,
        %(experiment_id)s,
        %(candidate_id)s,
        %(dataset_version)s,
        %(evaluation_provider)s,
        %(evaluation_result_id)s,
        %(started_at)s,
        %(completed_at)s,
        %(status)s,
        %(failure_reason)s,
        %(total_item_count)s,
        %(completed_item_count)s,
        %(evaluated_item_count)s
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        experiment_id = EXCLUDED.experiment_id,
        candidate_id = EXCLUDED.candidate_id,
        dataset_version = EXCLUDED.dataset_version,
        evaluation_provider = EXCLUDED.evaluation_provider,
        evaluation_result_id = EXCLUDED.evaluation_result_id,
        started_at = EXCLUDED.started_at,
        completed_at = EXCLUDED.completed_at,
        status = EXCLUDED.status,
        failure_reason = EXCLUDED.failure_reason,
        total_item_count = EXCLUDED.total_item_count,
        completed_item_count = EXCLUDED.completed_item_count,
        evaluated_item_count = EXCLUDED.evaluated_item_count
    """

    _SELECT_RUN_COLUMNS = """
    SELECT
        run_id,
        experiment_id,
        candidate_id,
        dataset_version,
        evaluation_provider,
        evaluation_result_id,
        started_at::text AS started_at,
        completed_at::text AS completed_at,
        status,
        failure_reason,
        total_item_count,
        completed_item_count,
        evaluated_item_count
    FROM evaluation_run
    """

    def __init__(
        self,
        database: PostgresDatabase,
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
                f"{self._SELECT_RUN_COLUMNS} WHERE run_id = %(run_id)s",
                {"run_id": run_id},
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
                "WHERE experiment_id = %(experiment_id)s "
                "ORDER BY started_at, run_id",
                {"experiment_id": experiment_id},
            ).fetchall()

        return EvaluationRunPersistenceMapper.from_persistence_records(rows)

    def find_by_candidate_id(
        self,
        candidate_id: str,
    ) -> list[EvaluationRun]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_RUN_COLUMNS} "
                "WHERE candidate_id = %(candidate_id)s "
                "ORDER BY started_at, run_id",
                {"candidate_id": candidate_id},
            ).fetchall()

        return EvaluationRunPersistenceMapper.from_persistence_records(rows)

    def find_all(self) -> list[EvaluationRun]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_RUN_COLUMNS} "
                "ORDER BY experiment_id, candidate_id, started_at, run_id"
            ).fetchall()

        return EvaluationRunPersistenceMapper.from_persistence_records(rows)
