"""Factory for JobRepository."""

from __future__ import annotations

import logging

from ai_governance.repositories.job_repository import JobRepository
from ai_governance.settings import Settings

logger = logging.getLogger(__name__)


class JobRepositoryFactory:
    """Selects the concrete JobRepository implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> JobRepository:
        backend = self._settings.job_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory job repository")
                from ai_governance.repositories import InMemoryJobRepository

                return InMemoryJobRepository()

            case "sqlite":
                path = self._settings.job_sqlite_path
                if not path:
                    raise ValueError(
                        "AI_GOVERNANCE_JOB_SQLITE_PATH is required when "
                        "AI_GOVERNANCE_JOB_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite job repository: %s", path)
                from ai_governance.repositories.sqlite.sqlite_job_repository import SQLiteJobRepository

                from ai_governance.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLiteJobRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.job_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_JOB_POSTGRES_DSN is required when "
                        "AI_GOVERNANCE_JOB_REPOSITORY=postgres"
                    )
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres import PostgresJobRepository

                database = PostgresDatabase(dsn)
                database.initialize()
                return PostgresJobRepository(database)

            case unknown:
                raise ValueError(
                    f"Unsupported job repository backend: {unknown}"
                )
