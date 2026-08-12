from __future__ import annotations

from typing import final

from snowflake.connector import DictCursor

from ai_governance.databases.snowflake.database import SnowflakeDatabase
from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.repositories.evaluation_repository import EvaluationRepository
from ai_governance.repositories.evaluation_repository import EvaluationResultPage
from ai_governance.repositories.mappers.evaluation_persistence_mapper import (
    EvaluationPersistenceMapper,
)
from ai_governance.repositories.snowflake._record_adapter import lowercase_records
from ai_governance.tenancy.domain import TenantContext


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
            TO_TIMESTAMP_TZ(%(created_at)s) AS created_at,
            %(organization_id)s AS organization_id,
            %(project_id)s AS project_id
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
        created_at = source.created_at,
        organization_id = source.organization_id,
        project_id = source.project_id
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
        created_at,
        organization_id,
        project_id
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
        source.created_at,
        source.organization_id,
        source.project_id
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
            AS created_at,
        organization_id,
        project_id
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
            AS created_at,
        organization_id,
        project_id
    FROM agent_evaluation
    WHERE evaluation_id = %(evaluation_id)s
    ORDER BY metric_name
    """

    _COUNT_BY_EXECUTION_PREFIX_SQL = """
    SELECT COUNT(DISTINCT evaluation_id)
    FROM agent_evaluation
    WHERE execution_id LIKE %(execution_id_prefix)s
      AND organization_id = %(organization_id)s
      AND project_id = %(project_id)s
    """

    _FIND_PAGE_BY_EXECUTION_PREFIX_SQL = """
    WITH selected AS (
        SELECT evaluation_id
        FROM agent_evaluation
        WHERE execution_id LIKE %(execution_id_prefix)s
          AND organization_id = %(organization_id)s
          AND project_id = %(project_id)s
        GROUP BY evaluation_id, execution_id, created_at
        ORDER BY created_at ASC, execution_id ASC, evaluation_id ASC
        LIMIT %(limit)s OFFSET %(offset)s
    )
    SELECT
        evaluation_id, execution_id, evaluator_type, evaluator_version,
        metric_name, metric_score, explanation,
        TO_JSON(metadata_json) AS metadata_json,
        TO_JSON(provider_metadata_json) AS provider_metadata_json,
        TO_JSON(provider_descriptor_snapshot_json) AS provider_descriptor_snapshot_json,
        TO_JSON(artifacts_json) AS artifacts_json,
        TO_VARCHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM') AS created_at,
        organization_id, project_id
    FROM agent_evaluation
    WHERE evaluation_id IN (SELECT evaluation_id FROM selected)
    ORDER BY created_at ASC, execution_id ASC, evaluation_id ASC, metric_name ASC
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

    def find_page_by_execution_id_prefix(
        self,
        execution_id_prefix: str,
        context: TenantContext,
        *,
        offset: int,
        limit: int,
    ) -> EvaluationResultPage:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                parameters = {
                    "execution_id_prefix": f"{execution_id_prefix}%",
                    "organization_id": context.organization_id,
                    "project_id": context.project_id or "",
                    "offset": offset,
                    "limit": limit,
                }
                cursor.execute(self._COUNT_BY_EXECUTION_PREFIX_SQL, parameters)
                total_count = cursor.fetchone()[0]
                cursor.execute(self._FIND_PAGE_BY_EXECUTION_PREFIX_SQL, parameters)
                rows = lowercase_records(cursor.fetchall())
        return EvaluationResultPage(
            items=tuple(EvaluationPersistenceMapper.from_persistence_records(rows)),
            total_count=total_count,
        )
