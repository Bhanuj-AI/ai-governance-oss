"""Factory for ExperimentCandidateRepository."""

from __future__ import annotations

import logging

from ai_governance.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from ai_governance.settings import Settings

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
                from ai_governance.repositories.in_memory_experiment_candidate_repository import (
                    InMemoryExperimentCandidateRepository,
                )

                return InMemoryExperimentCandidateRepository()

            case "sqlite":
                path = self._settings.experiment_candidate_sqlite_path
                if not path:
                    raise ValueError(
                        "AI_GOVERNANCE_EXPERIMENT_CANDIDATE_SQLITE_PATH is required when "
                        "AI_GOVERNANCE_EXPERIMENT_CANDIDATE_REPOSITORY=sqlite"
                    )
                logger.debug(
                    "Selected SQLite experiment candidate repository: %s", path
                )
                from ai_governance.repositories.sqlite.sqlite_experiment_candidate_repository import (
                    SQLiteExperimentCandidateRepository,
                )

                from ai_governance.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLiteExperimentCandidateRepository(
                    create_sqlite_database(path)
                )

            case "postgres":
                dsn = self._settings.experiment_candidate_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_EXPERIMENT_CANDIDATE_POSTGRES_DSN is required when "
                        "AI_GOVERNANCE_EXPERIMENT_CANDIDATE_REPOSITORY=postgres"
                    )
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres import PostgresExperimentCandidateRepository

                return PostgresExperimentCandidateRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported experiment candidate repository backend: {unknown}"
                )
