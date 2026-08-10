from __future__ import annotations

from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.experiments import Experiment
from ai_governance.repositories.experiment_repository import ExperimentRepository
from ai_governance.repositories.mappers.experiment_persistence_mapper import (
    ExperimentPersistenceMapper,
)


@final
class SQLiteExperimentRepository(ExperimentRepository):
    """
    SQLite implementation of the ExperimentRepository contract.
    """

    _INSERT_EXPERIMENT_SQL = """
    INSERT OR REPLACE INTO experiment (
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
        :experiment_id,
        :name,
        :description,
        :owner,
        :created_at,
        :updated_at,
        :status
        , :organization_id
        , :project_id
    )
    """

    _SELECT_EXPERIMENT_COLUMNS = """
    SELECT
        experiment_id,
        name,
        description,
        owner,
        created_at,
        updated_at,
        status
        , organization_id
        , project_id
    FROM experiment
    """

    def __init__(
        self,
        database: SQLiteDatabase,
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
                f"{self._SELECT_EXPERIMENT_COLUMNS} WHERE experiment_id = ?",
                (experiment_id,),
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
                f"{self._SELECT_EXPERIMENT_COLUMNS} WHERE name = ?",
                (name,),
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
