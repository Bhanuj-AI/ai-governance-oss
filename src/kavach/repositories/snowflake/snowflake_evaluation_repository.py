from __future__ import annotations

from typing import final

from snowflake.connector import DictCursor

from kavach.databases.snowflake.database import SnowflakeDatabase
from kavach.domain.evaluation_result import EvaluationResult
from kavach.repositories.evaluation_repository import EvaluationRepository
from kavach.repositories.mappers.evaluation_persistence_mapper import (
    EvaluationPersistenceMapper,
)
from kavach.repositories.snowflake._record_adapter import lowercase_records


@final
class SnowflakeEvaluationRepository(EvaluationRepository):
    """
    Snowflake implementation of the EvaluationRepository contract.
    """

    _MERGE_EVALUATION_SQL = """
    MERGE INTO agent_evaluation target
    USING (
        SELECT
            %(evaluation_id)s AS evaluation_id,
            %(execution_id)s AS execution_id,
            %(evaluator_type)s AS evaluator_type,
            %(evaluator_version)s AS evaluator_version,
            %(metric_name)s AS metric_name,
            %(metric_score)s AS metric_score,
            %(explanation)s AS explanation,
            PARSE_JSON(%(metadata_json)s) AS metadata_json,
            PARSE_JSON(%(provider_metadata_json)s) AS provider_metadata_json,
            PARSE_JSON(%(provider_descriptor_snapshot_json)s)
                AS provider_descriptor_snapshot_json,
            PARSE_JSON(%(artifacts_json)s) AS artifacts_json,
            TO_TIMESTAMP_TZ(%(created_at)s) AS created_at
    ) source
    ON target.evaluation_id = source.evaluation_id
       AND target.metric_name = source.metric_name
    WHEN MATCHED THEN UPDATE SET
        execution_id = source.execution_id,
        evaluator_type = source.evaluator_type,
        evaluator_version = source.evaluator_version,
        metric_score = source.metric_score,
        explanation = source.explanation,
        metadata_json = source.metadata_json,
        provider_metadata_json = source.provider_metadata_json,
        provider_descriptor_snapshot_json = source.provider_descriptor_snapshot_json,
        artifacts_json = source.artifacts_json,
        created_at = source.created_at
    WHEN NOT MATCHED THEN INSERT (
        evaluation_id,
        execution_id,
        evaluator_type,
        evaluator_version,
        metric_name,
        metric_score,
        explanation,
        metadata_json,
        provider_metadata_json,
        provider_descriptor_snapshot_json,
        artifacts_json,
        created_at
    )
    VALUES (
        source.evaluation_id,
        source.execution_id,
        source.evaluator_type,
        source.evaluator_version,
        source.metric_name,
        source.metric_score,
        source.explanation,
        source.metadata_json,
        source.provider_metadata_json,
        source.provider_descriptor_snapshot_json,
        source.artifacts_json,
        source.created_at
    )
    """

    _FIND_BY_EXECUTION_SQL = """
    SELECT
        evaluation_id,
        execution_id,
        evaluator_type,
        evaluator_version,
        metric_name,
        metric_score,
        explanation,
        TO_JSON(metadata_json) AS metadata_json,
        TO_JSON(provider_metadata_json) AS provider_metadata_json,
        TO_JSON(provider_descriptor_snapshot_json)
            AS provider_descriptor_snapshot_json,
        TO_JSON(artifacts_json) AS artifacts_json,
        TO_VARCHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')
            AS created_at
    FROM agent_evaluation
    WHERE execution_id = %(execution_id)s
    ORDER BY evaluation_id, metric_name
    """

    _FIND_BY_EVALUATION_SQL = """
    SELECT
        evaluation_id,
        execution_id,
        evaluator_type,
        evaluator_version,
        metric_name,
        metric_score,
        explanation,
        TO_JSON(metadata_json) AS metadata_json,
        TO_JSON(provider_metadata_json) AS provider_metadata_json,
        TO_JSON(provider_descriptor_snapshot_json)
            AS provider_descriptor_snapshot_json,
        TO_JSON(artifacts_json) AS artifacts_json,
        TO_VARCHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')
            AS created_at
    FROM agent_evaluation
    WHERE evaluation_id = %(evaluation_id)s
    ORDER BY metric_name
    """

    def __init__(
        self,
        database: SnowflakeDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        result: EvaluationResult,
    ) -> None:
        rows = EvaluationPersistenceMapper.to_persistence_records(result)

        with self._database.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    for row in rows:
                        cursor.execute(self._MERGE_EVALUATION_SQL, row)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_evaluation_id(
        self,
        evaluation_id: str,
    ) -> EvaluationResult | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    self._FIND_BY_EVALUATION_SQL,
                    {"evaluation_id": evaluation_id},
                )
                rows = lowercase_records(cursor.fetchall())

        if not rows:
            return None

        return EvaluationPersistenceMapper.from_persistence_records(rows)[0]

    def find_by_execution_id(
        self,
        execution_id: str,
    ) -> list[EvaluationResult]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    self._FIND_BY_EXECUTION_SQL,
                    {"execution_id": execution_id},
                )
                rows = lowercase_records(cursor.fetchall())

        if not rows:
            return []

        return EvaluationPersistenceMapper.from_persistence_records(rows)
