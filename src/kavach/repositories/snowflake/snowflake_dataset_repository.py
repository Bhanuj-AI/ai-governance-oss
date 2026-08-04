from __future__ import annotations

from typing import final

from snowflake.connector import DictCursor

from kavach.databases.snowflake.database import SnowflakeDatabase
from kavach.domain.datasets import Dataset
from kavach.repositories.dataset_repository import DatasetRepository
from kavach.repositories.mappers.dataset_persistence_mapper import (
    DatasetPersistenceMapper,
)
from kavach.repositories.snowflake._record_adapter import (
    lowercase_record,
    lowercase_records,
)


@final
class SnowflakeDatasetRepository(DatasetRepository):
    """
    Snowflake implementation of the DatasetRepository contract.
    """

    _MERGE_DATASET_SQL = """
    MERGE INTO dataset_registry target
    USING (
        SELECT
            %(dataset_id)s AS dataset_id,
            %(name)s AS name,
            %(version)s AS version,
            %(description)s AS description,
            %(storage_uri)s AS storage_uri,
            %(storage_type)s AS storage_type,
            %(schema_version)s AS schema_version,
            %(record_count)s AS record_count,
            %(checksum)s AS checksum,
            %(creator)s AS creator,
            TO_TIMESTAMP_TZ(%(created_at)s) AS created_at,
            %(status)s AS status,
            %(provenance)s AS provenance,
            %(source_system)s AS source_system,
            %(source_reference)s AS source_reference
    ) source
    ON target.dataset_id = source.dataset_id
    WHEN MATCHED THEN UPDATE SET
        name = source.name,
        version = source.version,
        description = source.description,
        storage_uri = source.storage_uri,
        storage_type = source.storage_type,
        schema_version = source.schema_version,
        record_count = source.record_count,
        checksum = source.checksum,
        creator = source.creator,
        created_at = source.created_at,
        status = source.status,
        provenance = source.provenance,
        source_system = source.source_system,
        source_reference = source.source_reference
    WHEN NOT MATCHED THEN INSERT (
        dataset_id,
        name,
        version,
        description,
        storage_uri,
        storage_type,
        schema_version,
        record_count,
        checksum,
        creator,
        created_at,
        status,
        provenance,
        source_system,
        source_reference
    )
    VALUES (
        source.dataset_id,
        source.name,
        source.version,
        source.description,
        source.storage_uri,
        source.storage_type,
        source.schema_version,
        source.record_count,
        source.checksum,
        source.creator,
        source.created_at,
        source.status,
        source.provenance,
        source.source_system,
        source.source_reference
    )
    """

    _SELECT_DATASET_COLUMNS = """
    SELECT
        dataset_id,
        name,
        version,
        description,
        storage_uri,
        storage_type,
        schema_version,
        record_count,
        checksum,
        creator,
        TO_VARCHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')
            AS created_at,
        status,
        provenance,
        source_system,
        source_reference
    FROM dataset_registry
    """

    def __init__(
        self,
        database: SnowflakeDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        dataset: Dataset,
    ) -> None:
        record = DatasetPersistenceMapper.to_persistence_record(dataset)

        with self._database.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(self._MERGE_DATASET_SQL, record)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        dataset_id: str,
    ) -> Dataset | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_DATASET_COLUMNS} "
                    "WHERE dataset_id = %(dataset_id)s",
                    {"dataset_id": dataset_id},
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return DatasetPersistenceMapper.from_persistence_record(
            lowercase_record(row)
        )

    def find_by_name(
        self,
        name: str,
    ) -> list[Dataset]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_DATASET_COLUMNS} "
                    "WHERE name = %(name)s "
                    "ORDER BY created_at, version",
                    {"name": name},
                )
                rows = lowercase_records(cursor.fetchall())

        return DatasetPersistenceMapper.from_persistence_records(rows)

    def find_by_name_and_version(
        self,
        name: str,
        version: str,
    ) -> Dataset | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_DATASET_COLUMNS} "
                    "WHERE name = %(name)s AND version = %(version)s",
                    {"name": name, "version": version},
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return DatasetPersistenceMapper.from_persistence_record(
            lowercase_record(row)
        )

    def find_all(self) -> list[Dataset]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_DATASET_COLUMNS} "
                    "ORDER BY name, created_at, version"
                )
                rows = lowercase_records(cursor.fetchall())

        return DatasetPersistenceMapper.from_persistence_records(rows)
