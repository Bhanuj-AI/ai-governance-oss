from __future__ import annotations

from typing import final

from kavach.databases.postgres.database import PostgresDatabase
from kavach.domain.experiments import Experiment
from kavach.repositories.experiment_repository import ExperimentRepository
from kavach.repositories.mappers.experiment_persistence_mapper import (
    ExperimentPersistenceMapper,
)


@final
class PostgresExperimentRepository(ExperimentRepository):
    """
    PostgreSQL implementation of the ExperimentRepository contract.
    """

    _INSERT_EXPERIMENT_SQL = """
    INSERT INTO experiment (
        experiment_id,
        name,
        description,
        owner,
        created_at,
        updated_at,
        status
        , organization_id
        , project_id
    )
    VALUES (
        %(experiment_id)s,
        %(name)s,
        %(description)s,
        %(owner)s,
        %(created_at)s,
        %(updated_at)s,
        %(status)s
        , %(organization_id)s
        , %(project_id)s
    )
    ON CONFLICT (experiment_id)
    DO UPDATE SET
        name = EXCLUDED.name,
        description = EXCLUDED.description,
        owner = EXCLUDED.owner,
        created_at = EXCLUDED.created_at,
        updated_at = EXCLUDED.updated_at,
        status = EXCLUDED.status,
        organization_id = EXCLUDED.organization_id,
        project_id = EXCLUDED.project_id
    """

    _SELECT_EXPERIMENT_COLUMNS = """
    SELECT
        experiment_id,
        name,
        description,
        owner,
        created_at::text AS created_at,
        updated_at::text AS updated_at,
        status,
        organization_id,
        project_id
    FROM experiment
    """

    def __init__(
        self,
        database: PostgresDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        experiment: Experiment,
    ) -> None:
        record = ExperimentPersistenceMapper.to_persistence_record(experiment)

        with self._database.connect() as connection:
            try:
                connection.execute(
                    self._INSERT_EXPERIMENT_SQL,
                    record,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        experiment_id: str,
    ) -> Experiment | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_EXPERIMENT_COLUMNS} "
                "WHERE experiment_id = %(experiment_id)s",
                {"experiment_id": experiment_id},
            ).fetchone()

        if row is None:
            return None

        return ExperimentPersistenceMapper.from_persistence_record(row)

    def find_by_name(
        self,
        name: str,
    ) -> Experiment | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_EXPERIMENT_COLUMNS} WHERE name = %(name)s",
                {"name": name},
            ).fetchone()

        if row is None:
            return None

        return ExperimentPersistenceMapper.from_persistence_record(row)

    def find_all(self) -> list[Experiment]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_EXPERIMENT_COLUMNS} ORDER BY created_at, name"
            ).fetchall()

        return ExperimentPersistenceMapper.from_persistence_records(rows)
