"""Factory for ExperimentCandidateRepository."""

from __future__ import annotations

import logging

from kavach.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from kavach.settings import Settings

logger = logging.getLogger(__name__)


class ExperimentCandidateRepositoryFactory:
    """Selects the concrete ExperimentCandidateRepository implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> ExperimentCandidateRepository:
        backend = self._settings.experiment_candidate_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory experiment candidate repository")
                from kavach.repositories.in_memory_experiment_candidate_repository import (
                    InMemoryExperimentCandidateRepository,
                )

                return InMemoryExperimentCandidateRepository()

            case "sqlite":
                path = self._settings.experiment_candidate_sqlite_path
                if not path:
                    raise ValueError(
                        "KAVACH_EXPERIMENT_CANDIDATE_SQLITE_PATH is required when "
                        "KAVACH_EXPERIMENT_CANDIDATE_REPOSITORY=sqlite"
                    )
                logger.debug(
                    "Selected SQLite experiment candidate repository: %s", path
                )
                from kavach.repositories.sqlite.sqlite_experiment_candidate_repository import (
                    SQLiteExperimentCandidateRepository,
                )

                from kavach.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLiteExperimentCandidateRepository(
                    create_sqlite_database(path)
                )

            case "postgres":
                dsn = self._settings.experiment_candidate_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "KAVACH_EXPERIMENT_CANDIDATE_POSTGRES_DSN is required when "
                        "KAVACH_EXPERIMENT_CANDIDATE_REPOSITORY=postgres"
                    )
                from kavach.databases.postgres.database import PostgresDatabase
                from kavach.repositories.postgres import PostgresExperimentCandidateRepository

                return PostgresExperimentCandidateRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported experiment candidate repository backend: {unknown}"
                )
