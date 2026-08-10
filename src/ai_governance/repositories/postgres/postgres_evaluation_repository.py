from __future__ import annotations

from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.repositories.evaluation_repository import EvaluationRepository
from ai_governance.repositories.mappers.evaluation_persistence_mapper import (
    EvaluationPersistenceMapper,
)
from ai_governance.repositories.postgres._record_adapter import with_jsonb_fields


@final
class PostgresEvaluationRepository(EvaluationRepository):
    """
    PostgreSQL implementation of the EvaluationRepository contract.
    """

    _INSERT_EVALUATION_SQL = """
    INSERT INTO agent_evaluation (
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
        , organization_id
        , project_id
    )
    VALUES (
        %(evaluation_id)s,
        %(execution_id)s,
        %(evaluator_type)s,
        %(evaluator_version)s,
        %(metric_name)s,
        %(metric_score)s,
        %(explanation)s,
        %(metadata_json)s,
        %(provider_metadata_json)s,
        %(provider_descriptor_snapshot_json)s,
        %(artifacts_json)s,
        %(created_at)s
        , %(organization_id)s
        , %(project_id)s
    )
    ON CONFLICT (evaluation_id, metric_name)
    DO UPDATE SET
        execution_id = EXCLUDED.execution_id,
        evaluator_type = EXCLUDED.evaluator_type,
        evaluator_version = EXCLUDED.evaluator_version,
        metric_score = EXCLUDED.metric_score,
        explanation = EXCLUDED.explanation,
        metadata_json = EXCLUDED.metadata_json,
        provider_metadata_json = EXCLUDED.provider_metadata_json,
        provider_descriptor_snapshot_json = EXCLUDED.provider_descriptor_snapshot_json,
        artifacts_json = EXCLUDED.artifacts_json,
        created_at = EXCLUDED.created_at,
        organization_id = EXCLUDED.organization_id,
        project_id = EXCLUDED.project_id
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
        metadata_json::text AS metadata_json,
        provider_metadata_json::text AS provider_metadata_json,
        provider_descriptor_snapshot_json::text AS provider_descriptor_snapshot_json,
        artifacts_json::text AS artifacts_json,
        created_at::text AS created_at,
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
        metadata_json::text AS metadata_json,
        provider_metadata_json::text AS provider_metadata_json,
        provider_descriptor_snapshot_json::text AS provider_descriptor_snapshot_json,
        artifacts_json::text AS artifacts_json,
        created_at::text AS created_at,
        organization_id,
        project_id
    FROM agent_evaluation
    WHERE evaluation_id = %(evaluation_id)s
    ORDER BY metric_name
    """

    def __init__(
        self,
        database: PostgresDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        result: EvaluationResult,
    ) -> None:
        rows = [
            with_jsonb_fields(
                record,
                "metadata_json",
                "provider_metadata_json",
                "provider_descriptor_snapshot_json",
                "artifacts_json",
            )
            for record in EvaluationPersistenceMapper.to_persistence_records(result)
        ]

        with self._database.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.executemany(
                        self._INSERT_EVALUATION_SQL,
                        rows,
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_evaluation_id(
        self,
        evaluation_id: str,
    ) -> EvaluationResult | None:
        with self._database.connect() as connection:
            rows = connection.execute(
                self._FIND_BY_EVALUATION_SQL,
                {"evaluation_id": evaluation_id},
            ).fetchall()

        if not rows:
            return None

        return EvaluationPersistenceMapper.from_persistence_records(rows)[0]

    def find_by_execution_id(
        self,
        execution_id: str,
    ) -> list[EvaluationResult]:
        with self._database.connect() as connection:
            rows = connection.execute(
                self._FIND_BY_EXECUTION_SQL,
                {"execution_id": execution_id},
            ).fetchall()

        if not rows:
            return []

        return EvaluationPersistenceMapper.from_persistence_records(rows)
