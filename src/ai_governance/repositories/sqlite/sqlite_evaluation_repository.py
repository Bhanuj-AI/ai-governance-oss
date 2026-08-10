from __future__ import annotations
from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.repositories.evaluation_repository import EvaluationRepository
from ai_governance.repositories.mappers.evaluation_persistence_mapper import (
    EvaluationPersistenceMapper,
)


@final
class SQLiteEvaluationRepository(EvaluationRepository):
    """
    SQLite implementation of the EvaluationRepository contract.

    This repository is responsible only for executing SQL.
    Serialization between the domain model and persistence records is
    delegated to EvaluationPersistenceMapper.
    """

    _INSERT_EVALUATION_SQL = """
    INSERT OR REPLACE INTO agent_evaluation (
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
        :evaluation_id,
        :execution_id,
        :evaluator_type,
        :evaluator_version,
        :metric_name,
        :metric_score,
        :explanation,
        :metadata_json,
        :provider_metadata_json,
        :provider_descriptor_snapshot_json,
        :artifacts_json,
        :created_at
        , :organization_id
        , :project_id
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
        metadata_json,
        provider_metadata_json,
        provider_descriptor_snapshot_json,
        artifacts_json,
        created_at
        , organization_id
        , project_id
    FROM agent_evaluation
    WHERE execution_id = ?
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
        metadata_json,
        provider_metadata_json,
        provider_descriptor_snapshot_json,
        artifacts_json,
        created_at
        , organization_id
        , project_id
    FROM agent_evaluation
    WHERE evaluation_id = ?
    ORDER BY metric_name
    """

    def __init__(
        self,
        database: SQLiteDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        result: EvaluationResult,
    ) -> None:
        rows = EvaluationPersistenceMapper.to_persistence_records(result)

        with self._database.connect() as connection:
            try:
                connection.executemany(
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
                (evaluation_id,),
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
                (execution_id,),
            ).fetchall()

        if not rows:
            return []

        return EvaluationPersistenceMapper.from_persistence_records(rows)
