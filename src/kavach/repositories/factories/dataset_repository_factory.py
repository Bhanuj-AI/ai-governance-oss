"""Factory for DatasetRepository."""

from __future__ import annotations

import logging

from kavach.repositories.dataset_repository import DatasetRepository
from kavach.settings import Settings

logger = logging.getLogger(__name__)


class DatasetRepositoryFactory:
    """Selects the concrete DatasetRepository implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> DatasetRepository:
        backend = self._settings.dataset_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory dataset repository")
                from kavach.repositories.in_memory_dataset_repository import (
                    InMemoryDatasetRepository,
                )

                return InMemoryDatasetRepository()

            case "sqlite":
                path = self._settings.dataset_sqlite_path
                if not path:
                    raise ValueError(
                        "KAVACH_DATASET_SQLITE_PATH is required when "
                        "KAVACH_DATASET_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite dataset repository: %s", path)
                from kavach.repositories.sqlite.sqlite_dataset_repository import SQLiteDatasetRepository

                from kavach.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLiteDatasetRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.dataset_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "KAVACH_DATASET_POSTGRES_DSN is required when "
                        "KAVACH_DATASET_REPOSITORY=postgres"
                    )
                from kavach.databases.postgres.database import PostgresDatabase
                from kavach.repositories.postgres import PostgresDatasetRepository

                return PostgresDatasetRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported dataset repository backend: {unknown}"
                )
