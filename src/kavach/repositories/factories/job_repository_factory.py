"""Factory for JobRepository."""

from __future__ import annotations

import logging

from kavach.repositories.job_repository import JobRepository
from kavach.settings import Settings

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
                from kavach.repositories import InMemoryJobRepository

                return InMemoryJobRepository()

            case "sqlite":
                path = self._settings.job_sqlite_path
                if not path:
                    raise ValueError(
                        "KAVACH_JOB_SQLITE_PATH is required when "
                        "KAVACH_JOB_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite job repository: %s", path)
                from kavach.repositories.sqlite.sqlite_job_repository import SQLiteJobRepository

                from kavach.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLiteJobRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.job_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "KAVACH_JOB_POSTGRES_DSN is required when "
                        "KAVACH_JOB_REPOSITORY=postgres"
                    )
                from kavach.databases.postgres.database import PostgresDatabase
                from kavach.repositories.postgres import PostgresJobRepository

                database = PostgresDatabase(dsn)
                database.initialize()
                return PostgresJobRepository(database)

            case unknown:
                raise ValueError(
                    f"Unsupported job repository backend: {unknown}"
                )
