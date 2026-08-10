from __future__ import annotations

from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.experiments import ExperimentCandidate
from ai_governance.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from ai_governance.repositories.mappers.experiment_candidate_persistence_mapper import (
    ExperimentCandidatePersistenceMapper,
)
from ai_governance.repositories.postgres._record_adapter import with_jsonb_fields


@final
class PostgresExperimentCandidateRepository(
    ExperimentCandidateRepository
):
    """
    PostgreSQL implementation of the ExperimentCandidateRepository contract.
    """

    _INSERT_CANDIDATE_SQL = """
    INSERT INTO experiment_candidate (
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
        %(candidate_id)s,
        %(experiment_id)s,
        %(name)s,
        %(prompt_id)s,
        %(prompt_version)s,
        %(model_id)s,
        %(model_version)s,
        %(dataset_id)s,
        %(dataset_version)s,
        %(evaluation_provider)s,
        %(temperature)s,
        %(top_p)s,
        %(max_tokens)s,
        %(metadata_json)s,
        %(created_at)s
    )
    ON CONFLICT (candidate_id)
    DO UPDATE SET
        experiment_id = EXCLUDED.experiment_id,
        name = EXCLUDED.name,
        prompt_id = EXCLUDED.prompt_id,
        prompt_version = EXCLUDED.prompt_version,
        model_id = EXCLUDED.model_id,
        model_version = EXCLUDED.model_version,
        dataset_id = EXCLUDED.dataset_id,
        dataset_version = EXCLUDED.dataset_version,
        evaluation_provider = EXCLUDED.evaluation_provider,
        temperature = EXCLUDED.temperature,
        top_p = EXCLUDED.top_p,
        max_tokens = EXCLUDED.max_tokens,
        metadata_json = EXCLUDED.metadata_json,
        created_at = EXCLUDED.created_at
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
        metadata_json::text AS metadata_json,
        created_at::text AS created_at
    FROM experiment_candidate
    """

    def __init__(
        self,
        database: PostgresDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        candidate: ExperimentCandidate,
    ) -> None:
        record = with_jsonb_fields(
            ExperimentCandidatePersistenceMapper.to_persistence_record(
                candidate
            ),
            "metadata_json",
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
                f"{self._SELECT_CANDIDATE_COLUMNS} "
                "WHERE candidate_id = %(candidate_id)s",
                {"candidate_id": candidate_id},
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
                "WHERE experiment_id = %(experiment_id)s "
                "ORDER BY created_at, name",
                {"experiment_id": experiment_id},
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
