"""Factory for ExperimentRepository."""

from __future__ import annotations

import logging

from kavach.repositories.experiment_repository import ExperimentRepository
from kavach.settings import Settings

logger = logging.getLogger(__name__)


class ExperimentRepositoryFactory:
    """Selects the concrete ExperimentRepository implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> ExperimentRepository:
        backend = self._settings.experiment_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory experiment repository")
                from kavach.repositories.in_memory_experiment_repository import (
                    InMemoryExperimentRepository,
                )

                return InMemoryExperimentRepository()

            case "sqlite":
                path = self._settings.experiment_sqlite_path
                if not path:
                    raise ValueError(
                        "KAVACH_EXPERIMENT_SQLITE_PATH is required when "
                        "KAVACH_EXPERIMENT_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite experiment repository: %s", path)
                from kavach.repositories.sqlite.sqlite_experiment_repository import SQLiteExperimentRepository

                from kavach.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLiteExperimentRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.experiment_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "KAVACH_EXPERIMENT_POSTGRES_DSN is required when "
                        "KAVACH_EXPERIMENT_REPOSITORY=postgres"
                    )
                from kavach.databases.postgres.database import PostgresDatabase
                from kavach.repositories.postgres import PostgresExperimentRepository

                return PostgresExperimentRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported experiment repository backend: {unknown}"
                )
