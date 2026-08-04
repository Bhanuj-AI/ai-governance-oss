from __future__ import annotations

from typing import final

from kavach.databases.postgres.database import PostgresDatabase
from kavach.domain.datasets import Dataset
from kavach.repositories.dataset_repository import DatasetRepository
from kavach.repositories.mappers.dataset_persistence_mapper import (
    DatasetPersistenceMapper,
)


@final
class PostgresDatasetRepository(DatasetRepository):
    """
    PostgreSQL implementation of the DatasetRepository contract.
    """

    _INSERT_DATASET_SQL = """
    INSERT INTO dataset_registry (
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
        organization_id,
        project_id,
        provenance,
        source_system,
        source_reference
    )
    VALUES (
        %(dataset_id)s,
        %(name)s,
        %(version)s,
        %(description)s,
        %(storage_uri)s,
        %(storage_type)s,
        %(schema_version)s,
        %(record_count)s,
        %(checksum)s,
        %(creator)s,
        %(created_at)s,
        %(status)s,
        %(organization_id)s,
        %(project_id)s,
        %(provenance)s,
        %(source_system)s,
        %(source_reference)s
    )
    ON CONFLICT (dataset_id)
    DO UPDATE SET
        name = EXCLUDED.name,
        version = EXCLUDED.version,
        description = EXCLUDED.description,
        storage_uri = EXCLUDED.storage_uri,
        storage_type = EXCLUDED.storage_type,
        schema_version = EXCLUDED.schema_version,
        record_count = EXCLUDED.record_count,
        checksum = EXCLUDED.checksum,
        creator = EXCLUDED.creator,
        created_at = EXCLUDED.created_at,
        status = EXCLUDED.status,
        organization_id = EXCLUDED.organization_id,
        project_id = EXCLUDED.project_id,
        provenance = EXCLUDED.provenance,
        source_system = EXCLUDED.source_system,
        source_reference = EXCLUDED.source_reference
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
        created_at::text AS created_at,
        status,
        organization_id,
        project_id,
        provenance,
        source_system,
        source_reference
    FROM dataset_registry
    """

    def __init__(
        self,
        database: PostgresDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        dataset: Dataset,
    ) -> None:
        record = DatasetPersistenceMapper.to_persistence_record(dataset)

        with self._database.connect() as connection:
            try:
                connection.execute(
                    self._INSERT_DATASET_SQL,
                    record,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        dataset_id: str,
    ) -> Dataset | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_DATASET_COLUMNS} WHERE dataset_id = %(dataset_id)s",
                {"dataset_id": dataset_id},
            ).fetchone()

        if row is None:
            return None

        return DatasetPersistenceMapper.from_persistence_record(row)

    def find_by_name(
        self,
        name: str,
    ) -> list[Dataset]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_DATASET_COLUMNS} "
                "WHERE name = %(name)s "
                "ORDER BY created_at, version",
                {"name": name},
            ).fetchall()

        return DatasetPersistenceMapper.from_persistence_records(rows)

    def find_by_name_and_version(
        self,
        name: str,
        version: str,
    ) -> Dataset | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_DATASET_COLUMNS} "
                "WHERE name = %(name)s AND version = %(version)s",
                {"name": name, "version": version},
            ).fetchone()

        if row is None:
            return None

        return DatasetPersistenceMapper.from_persistence_record(row)

    def find_all(self) -> list[Dataset]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_DATASET_COLUMNS} ORDER BY name, created_at, version"
            ).fetchall()

        return DatasetPersistenceMapper.from_persistence_records(rows)
