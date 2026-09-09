from __future__ import annotations

from typing import final

from snowflake.connector import DictCursor

from ai_governance.databases.snowflake.database import SnowflakeDatabase
from ai_governance.domain.experiments import EvaluationRun
from ai_governance.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from ai_governance.repositories.mappers.evaluation_run_persistence_mapper import (
    EvaluationRunPersistenceMapper,
)
from ai_governance.repositories.snowflake._record_adapter import (
    lowercase_record,
    lowercase_records,
)


@final
class SnowflakeEvaluationRunRepository(EvaluationRunRepository):
    """
    Snowflake implementation of the EvaluationRunRepository contract.
    """

    _MERGE_RUN_SQL = """
    MERGE INTO evaluation_run target
    USING (
        SELECT
            %(run_id)s AS run_id,
            %(experiment_id)s AS experiment_id,
            %(candidate_id)s AS candidate_id,
            %(dataset_version)s AS dataset_version,
            %(evaluation_provider)s AS evaluation_provider,
            %(evaluation_result_id)s AS evaluation_result_id,
            TO_TIMESTAMP_TZ(%(started_at)s) AS started_at,
            TO_TIMESTAMP_TZ(%(completed_at)s) AS completed_at,
            %(status)s AS status,
            %(failure_reason)s AS failure_reason,
            %(total_item_count)s AS total_item_count,
            %(completed_item_count)s AS completed_item_count,
            %(evaluated_item_count)s AS evaluated_item_count,
            PARSE_JSON(%(runner_provenance_json)s) AS runner_provenance_json
    ) source
    ON target.run_id = source.run_id
    WHEN MATCHED THEN UPDATE SET
        experiment_id = source.experiment_id,
        candidate_id = source.candidate_id,
        dataset_version = source.dataset_version,
        evaluation_provider = source.evaluation_provider,
        evaluation_result_id = source.evaluation_result_id,
        started_at = source.started_at,
        completed_at = source.completed_at,
        status = source.status,
        failure_reason = source.failure_reason,
        total_item_count = source.total_item_count,
        completed_item_count = source.completed_item_count,
        evaluated_item_count = source.evaluated_item_count
        , runner_provenance_json = source.runner_provenance_json
    WHEN NOT MATCHED THEN INSERT (
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
        evaluated_item_count,
        runner_provenance_json
    )
    VALUES (
        source.run_id,
        source.experiment_id,
        source.candidate_id,
        source.dataset_version,
        source.evaluation_provider,
        source.evaluation_result_id,
        source.started_at,
        source.completed_at,
        source.status,
        source.failure_reason,
        source.total_item_count,
        source.completed_item_count,
        source.evaluated_item_count,
        source.runner_provenance_json
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
        TO_VARCHAR(started_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')
            AS started_at,
        TO_VARCHAR(completed_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')
            AS completed_at,
        status,
        failure_reason,
        total_item_count,
        completed_item_count,
        evaluated_item_count,
        TO_JSON(runner_provenance_json) AS runner_provenance_json
    FROM evaluation_run
    """

    def __init__(
        self,
        database: SnowflakeDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        run: EvaluationRun,
    ) -> None:
        record = EvaluationRunPersistenceMapper.to_persistence_record(run)

        with self._database.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(self._MERGE_RUN_SQL, record)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        run_id: str,
    ) -> EvaluationRun | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_RUN_COLUMNS} WHERE run_id = %(run_id)s",
                    {"run_id": run_id},
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return EvaluationRunPersistenceMapper.from_persistence_record(
            lowercase_record(row)
        )

    def find_by_experiment_id(
        self,
        experiment_id: str,
    ) -> list[EvaluationRun]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_RUN_COLUMNS} "
                    "WHERE experiment_id = %(experiment_id)s "
                    "ORDER BY started_at, run_id",
                    {"experiment_id": experiment_id},
                )
                rows = lowercase_records(cursor.fetchall())

        return EvaluationRunPersistenceMapper.from_persistence_records(rows)

    def find_by_candidate_id(
        self,
        candidate_id: str,
    ) -> list[EvaluationRun]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_RUN_COLUMNS} "
                    "WHERE candidate_id = %(candidate_id)s "
                    "ORDER BY started_at, run_id",
                    {"candidate_id": candidate_id},
                )
                rows = lowercase_records(cursor.fetchall())

        return EvaluationRunPersistenceMapper.from_persistence_records(rows)

    def find_all(self) -> list[EvaluationRun]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_RUN_COLUMNS} "
                    "ORDER BY experiment_id, candidate_id, started_at, run_id"
                )
                rows = lowercase_records(cursor.fetchall())

        return EvaluationRunPersistenceMapper.from_persistence_records(rows)
