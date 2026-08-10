from __future__ import annotations

from typing import final

from snowflake.connector import DictCursor

from ai_governance.databases.snowflake.database import SnowflakeDatabase
from ai_governance.domain.models import Model
from ai_governance.repositories.mappers.model_persistence_mapper import (
    ModelPersistenceMapper,
)
from ai_governance.repositories.model_repository import ModelRepository
from ai_governance.repositories.snowflake._record_adapter import (
    lowercase_record,
    lowercase_records,
)


@final
class SnowflakeModelRepository(ModelRepository):
    """
    Snowflake implementation of the ModelRepository contract.
    """

    _MERGE_MODEL_SQL = """
    MERGE INTO model_registry target
    USING (
        SELECT
            %(model_id)s AS model_id,
            %(provider)s AS provider,
            %(model_name)s AS model_name,
            %(version)s AS version,
            PARSE_JSON(%(parameters_json)s) AS parameters_json,
            PARSE_JSON(%(cost_json)s) AS cost_json,
            %(latency)s AS latency,
            %(context_window)s AS context_window,
            %(creator)s AS creator,
            TO_TIMESTAMP_TZ(%(created_at)s) AS created_at,
            %(status)s AS status,
            %(provenance)s AS provenance,
            %(source_system)s AS source_system,
            %(source_reference)s AS source_reference
    ) source
    ON target.model_id = source.model_id
    WHEN MATCHED THEN UPDATE SET
        provider = source.provider,
        model_name = source.model_name,
        version = source.version,
        parameters_json = source.parameters_json,
        cost_json = source.cost_json,
        latency = source.latency,
        context_window = source.context_window,
        creator = source.creator,
        created_at = source.created_at,
        status = source.status,
        provenance = source.provenance,
        source_system = source.source_system,
        source_reference = source.source_reference
    WHEN NOT MATCHED THEN INSERT (
        model_id,
        provider,
        model_name,
        version,
        parameters_json,
        cost_json,
        latency,
        context_window,
        creator,
        created_at,
        status,
        provenance,
        source_system,
        source_reference
    )
    VALUES (
        source.model_id,
        source.provider,
        source.model_name,
        source.version,
        source.parameters_json,
        source.cost_json,
        source.latency,
        source.context_window,
        source.creator,
        source.created_at,
        source.status,
        source.provenance,
        source.source_system,
        source.source_reference
    )
    """

    _SELECT_MODEL_COLUMNS = """
    SELECT
        model_id,
        provider,
        model_name,
        version,
        TO_JSON(parameters_json) AS parameters_json,
        TO_JSON(cost_json) AS cost_json,
        latency,
        context_window,
        creator,
        TO_VARCHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')
            AS created_at,
        status,
        provenance,
        source_system,
        source_reference
    FROM model_registry
    """

    def __init__(
        self,
        database: SnowflakeDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        model: Model,
    ) -> None:
        record = ModelPersistenceMapper.to_persistence_record(model)

        with self._database.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(self._MERGE_MODEL_SQL, record)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        model_id: str,
    ) -> Model | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_MODEL_COLUMNS} "
                    "WHERE model_id = %(model_id)s",
                    {"model_id": model_id},
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return ModelPersistenceMapper.from_persistence_record(
            lowercase_record(row)
        )

    def find_by_logical_model(
        self,
        provider: str,
        model_name: str,
    ) -> list[Model]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_MODEL_COLUMNS} "
                    "WHERE provider = %(provider)s "
                    "AND model_name = %(model_name)s "
                    "ORDER BY created_at, version",
                    {"provider": provider, "model_name": model_name},
                )
                rows = lowercase_records(cursor.fetchall())

        return ModelPersistenceMapper.from_persistence_records(rows)

    def find_by_provider_name_and_version(
        self,
        provider: str,
        model_name: str,
        version: str,
    ) -> Model | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_MODEL_COLUMNS} "
                    "WHERE provider = %(provider)s "
                    "AND model_name = %(model_name)s "
                    "AND version = %(version)s",
                    {
                        "provider": provider,
                        "model_name": model_name,
                        "version": version,
                    },
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return ModelPersistenceMapper.from_persistence_record(
            lowercase_record(row)
        )

    def find_all(self) -> list[Model]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_MODEL_COLUMNS} "
                    "ORDER BY provider, model_name, created_at, version"
                )
                rows = lowercase_records(cursor.fetchall())

        return ModelPersistenceMapper.from_persistence_records(rows)
