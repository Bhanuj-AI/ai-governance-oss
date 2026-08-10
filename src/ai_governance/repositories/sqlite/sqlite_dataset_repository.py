from __future__ import annotations

from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.datasets import Dataset
from ai_governance.repositories.dataset_repository import DatasetRepository
from ai_governance.repositories.mappers.dataset_persistence_mapper import (
    DatasetPersistenceMapper,
)


@final
class SQLiteDatasetRepository(DatasetRepository):
    """
    SQLite implementation of the DatasetRepository contract.
    """

    _INSERT_DATASET_SQL = """
    INSERT OR REPLACE INTO dataset_registry (
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
        :dataset_id,
        :name,
        :version,
        :description,
        :storage_uri,
        :storage_type,
        :schema_version,
        :record_count,
        :checksum,
        :creator,
        :created_at,
        :status,
        :organization_id,
        :project_id,
        :provenance,
        :source_system,
        :source_reference
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
        created_at,
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
        database: SQLiteDatabase,
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
                f"{self._SELECT_DATASET_COLUMNS} WHERE dataset_id = ?",
                (dataset_id,),
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
                "WHERE name = ? "
                "ORDER BY created_at, version",
                (name,),
            ).fetchall()

        return DatasetPersistenceMapper.from_persistence_records(rows)

    def find_by_name_and_version(
        self,
        name: str,
        version: str,
    ) -> Dataset | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_DATASET_COLUMNS} WHERE name = ? AND version = ?",
                (name, version),
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
