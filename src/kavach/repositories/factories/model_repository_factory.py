"""Factory for ModelRepository."""

from __future__ import annotations

import logging

from kavach.repositories.model_repository import ModelRepository
from kavach.settings import Settings

logger = logging.getLogger(__name__)


class ModelRepositoryFactory:
    """Selects the concrete ModelRepository implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> ModelRepository:
        backend = self._settings.model_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory model repository")
                from kavach.repositories.in_memory_model_repository import (
                    InMemoryModelRepository,
                )

                return InMemoryModelRepository()

            case "sqlite":
                path = self._settings.model_sqlite_path
                if not path:
                    raise ValueError(
                        "KAVACH_MODEL_SQLITE_PATH is required when "
                        "KAVACH_MODEL_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite model repository: %s", path)
                from kavach.repositories.sqlite.sqlite_model_repository import SQLiteModelRepository

                from kavach.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLiteModelRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.model_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "KAVACH_MODEL_POSTGRES_DSN is required when "
                        "KAVACH_MODEL_REPOSITORY=postgres"
                    )
                from kavach.databases.postgres.database import PostgresDatabase
                from kavach.repositories.postgres import PostgresModelRepository

                return PostgresModelRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported model repository backend: {unknown}"
                )
