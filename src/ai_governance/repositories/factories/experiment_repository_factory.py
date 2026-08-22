"""Factory for ExperimentRepository."""

from __future__ import annotations

import logging

from ai_governance.repositories.experiment_repository import ExperimentRepository
from ai_governance.settings import Settings

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
                from ai_governance.repositories.in_memory_experiment_repository import (
                    InMemoryExperimentRepository,
                )

                return InMemoryExperimentRepository()

            case "sqlite":
                path = self._settings.experiment_sqlite_path
                if not path:
                    raise ValueError(
                        "AI_GOVERNANCE_EXPERIMENT_SQLITE_PATH is required when "
                        "AI_GOVERNANCE_EXPERIMENT_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite experiment repository: %s", path)
                from ai_governance.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )
                from ai_governance.repositories.sqlite.sqlite_experiment_repository import (
                    SQLiteExperimentRepository,
                )

                return SQLiteExperimentRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.experiment_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_EXPERIMENT_POSTGRES_DSN is required when "
                        "AI_GOVERNANCE_EXPERIMENT_REPOSITORY=postgres"
                    )
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres import (
                    PostgresExperimentRepository,
                )

                return PostgresExperimentRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported experiment repository backend: {unknown}"
                )
