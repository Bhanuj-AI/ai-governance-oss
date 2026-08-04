from __future__ import annotations

from typing import final

from snowflake.connector import DictCursor

from kavach.databases.snowflake.database import SnowflakeDatabase
from kavach.domain.experiments import Experiment
from kavach.repositories.experiment_repository import ExperimentRepository
from kavach.repositories.mappers.experiment_persistence_mapper import (
    ExperimentPersistenceMapper,
)
from kavach.repositories.snowflake._record_adapter import (
    lowercase_record,
    lowercase_records,
)


@final
class SnowflakeExperimentRepository(ExperimentRepository):
    """
    Snowflake implementation of the ExperimentRepository contract.
    """

    _MERGE_EXPERIMENT_SQL = """
    MERGE INTO experiment target
    USING (
        SELECT
            %(experiment_id)s AS experiment_id,
            %(name)s AS name,
            %(description)s AS description,
            %(owner)s AS owner,
            TO_TIMESTAMP_TZ(%(created_at)s) AS created_at,
            TO_TIMESTAMP_TZ(%(updated_at)s) AS updated_at,
            %(status)s AS status
    ) source
    ON target.experiment_id = source.experiment_id
    WHEN MATCHED THEN UPDATE SET
        name = source.name,
        description = source.description,
        owner = source.owner,
        created_at = source.created_at,
        updated_at = source.updated_at,
        status = source.status
    WHEN NOT MATCHED THEN INSERT (
        experiment_id,
        name,
        description,
        owner,
        created_at,
        updated_at,
        status
    )
    VALUES (
        source.experiment_id,
        source.name,
        source.description,
        source.owner,
        source.created_at,
        source.updated_at,
        source.status
    )
    """

    _SELECT_EXPERIMENT_COLUMNS = """
    SELECT
        experiment_id,
        name,
        description,
        owner,
        TO_VARCHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')
            AS created_at,
        TO_VARCHAR(updated_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')
            AS updated_at,
        status
    FROM experiment
    """

    def __init__(
        self,
        database: SnowflakeDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        experiment: Experiment,
    ) -> None:
        record = ExperimentPersistenceMapper.to_persistence_record(experiment)

        with self._database.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(self._MERGE_EXPERIMENT_SQL, record)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        experiment_id: str,
    ) -> Experiment | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_EXPERIMENT_COLUMNS} "
                    "WHERE experiment_id = %(experiment_id)s",
                    {"experiment_id": experiment_id},
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return ExperimentPersistenceMapper.from_persistence_record(
            lowercase_record(row)
        )

    def find_by_name(
        self,
        name: str,
    ) -> Experiment | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_EXPERIMENT_COLUMNS} "
                    "WHERE name = %(name)s",
                    {"name": name},
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return ExperimentPersistenceMapper.from_persistence_record(
            lowercase_record(row)
        )

    def find_all(self) -> list[Experiment]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_EXPERIMENT_COLUMNS} "
                    "ORDER BY created_at, name"
                )
                rows = lowercase_records(cursor.fetchall())

        return ExperimentPersistenceMapper.from_persistence_records(rows)
