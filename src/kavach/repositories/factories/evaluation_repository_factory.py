"""Factory for EvaluationRepository."""

from __future__ import annotations

import logging

from kavach.repositories.evaluation_repository import EvaluationRepository
from kavach.settings import Settings

logger = logging.getLogger(__name__)


class EvaluationRepositoryFactory:
    """Selects the concrete EvaluationRepository implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> EvaluationRepository:
        backend = self._settings.evaluation_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory evaluation repository")
                from kavach.repositories.in_memory_evaluation_repository import (
                    InMemoryEvaluationRepository,
                )

                return InMemoryEvaluationRepository()

            case "sqlite":
                path = self._settings.evaluation_sqlite_path
                if not path:
                    raise ValueError(
                        "KAVACH_EVALUATION_SQLITE_PATH is required when "
                        "KAVACH_EVALUATION_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite evaluation repository: %s", path)
                from kavach.repositories.sqlite.sqlite_evaluation_repository import SQLiteEvaluationRepository

                from kavach.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLiteEvaluationRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.evaluation_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "KAVACH_EVALUATION_POSTGRES_DSN is required when "
                        "KAVACH_EVALUATION_REPOSITORY=postgres"
                    )
                from kavach.databases.postgres.database import PostgresDatabase
                from kavach.repositories.postgres import PostgresEvaluationRepository

                return PostgresEvaluationRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported evaluation repository backend: {unknown}"
                )
