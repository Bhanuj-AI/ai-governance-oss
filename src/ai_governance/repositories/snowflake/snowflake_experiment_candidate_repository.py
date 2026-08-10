from __future__ import annotations

from typing import final

from snowflake.connector import DictCursor

from ai_governance.databases.snowflake.database import SnowflakeDatabase
from ai_governance.domain.experiments import ExperimentCandidate
from ai_governance.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from ai_governance.repositories.mappers.experiment_candidate_persistence_mapper import (
    ExperimentCandidatePersistenceMapper,
)
from ai_governance.repositories.snowflake._record_adapter import (
    lowercase_record,
    lowercase_records,
)


@final
class SnowflakeExperimentCandidateRepository(
    ExperimentCandidateRepository
):
    """
    Snowflake implementation of the ExperimentCandidateRepository contract.
    """

    _MERGE_CANDIDATE_SQL = """
    MERGE INTO experiment_candidate target
    USING (
        SELECT
            %(candidate_id)s AS candidate_id,
            %(experiment_id)s AS experiment_id,
            %(name)s AS name,
            %(prompt_id)s AS prompt_id,
            %(prompt_version)s AS prompt_version,
            %(model_id)s AS model_id,
            %(model_version)s AS model_version,
            %(dataset_id)s AS dataset_id,
            %(dataset_version)s AS dataset_version,
            %(evaluation_provider)s AS evaluation_provider,
            %(temperature)s AS temperature,
            %(top_p)s AS top_p,
            %(max_tokens)s AS max_tokens,
            PARSE_JSON(%(metadata_json)s) AS metadata_json,
            TO_TIMESTAMP_TZ(%(created_at)s) AS created_at
    ) source
    ON target.candidate_id = source.candidate_id
    WHEN MATCHED THEN UPDATE SET
        experiment_id = source.experiment_id,
        name = source.name,
        prompt_id = source.prompt_id,
        prompt_version = source.prompt_version,
        model_id = source.model_id,
        model_version = source.model_version,
        dataset_id = source.dataset_id,
        dataset_version = source.dataset_version,
        evaluation_provider = source.evaluation_provider,
        temperature = source.temperature,
        top_p = source.top_p,
        max_tokens = source.max_tokens,
        metadata_json = source.metadata_json,
        created_at = source.created_at
    WHEN NOT MATCHED THEN INSERT (
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
        source.candidate_id,
        source.experiment_id,
        source.name,
        source.prompt_id,
        source.prompt_version,
        source.model_id,
        source.model_version,
        source.dataset_id,
        source.dataset_version,
        source.evaluation_provider,
        source.temperature,
        source.top_p,
        source.max_tokens,
        source.metadata_json,
        source.created_at
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
        TO_JSON(metadata_json) AS metadata_json,
        TO_VARCHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')
            AS created_at
    FROM experiment_candidate
    """

    def __init__(
        self,
        database: SnowflakeDatabase,
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
                with connection.cursor() as cursor:
                    cursor.execute(self._MERGE_CANDIDATE_SQL, record)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        candidate_id: str,
    ) -> ExperimentCandidate | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_CANDIDATE_COLUMNS} "
                    "WHERE candidate_id = %(candidate_id)s",
                    {"candidate_id": candidate_id},
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return ExperimentCandidatePersistenceMapper.from_persistence_record(
            lowercase_record(row)
        )

    def find_by_experiment_id(
        self,
        experiment_id: str,
    ) -> list[ExperimentCandidate]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_CANDIDATE_COLUMNS} "
                    "WHERE experiment_id = %(experiment_id)s "
                    "ORDER BY created_at, name",
                    {"experiment_id": experiment_id},
                )
                rows = lowercase_records(cursor.fetchall())

        return ExperimentCandidatePersistenceMapper.from_persistence_records(
            rows
        )

    def find_all(self) -> list[ExperimentCandidate]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_CANDIDATE_COLUMNS} "
                    "ORDER BY experiment_id, created_at, name"
                )
                rows = lowercase_records(cursor.fetchall())

        return ExperimentCandidatePersistenceMapper.from_persistence_records(
            rows
        )
