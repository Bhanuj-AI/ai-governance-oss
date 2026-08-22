"""Factory for EvaluationRepository."""

from __future__ import annotations

import logging

from ai_governance.repositories.evaluation_repository import EvaluationRepository
from ai_governance.settings import Settings

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
                from ai_governance.repositories.in_memory_evaluation_repository import (
                    InMemoryEvaluationRepository,
                )

                return InMemoryEvaluationRepository()

            case "sqlite":
                path = self._settings.evaluation_sqlite_path
                if not path:
                    raise ValueError(
                        "AI_GOVERNANCE_EVALUATION_SQLITE_PATH is required when "
                        "AI_GOVERNANCE_EVALUATION_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite evaluation repository: %s", path)
                from ai_governance.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )
                from ai_governance.repositories.sqlite.sqlite_evaluation_repository import (
                    SQLiteEvaluationRepository,
                )

                return SQLiteEvaluationRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.evaluation_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_EVALUATION_POSTGRES_DSN is required when "
                        "AI_GOVERNANCE_EVALUATION_REPOSITORY=postgres"
                    )
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres import (
                    PostgresEvaluationRepository,
                )

                return PostgresEvaluationRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported evaluation repository backend: {unknown}"
                )
