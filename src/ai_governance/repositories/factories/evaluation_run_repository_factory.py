"""Factory for EvaluationRunRepository."""

from __future__ import annotations

import logging

from ai_governance.repositories.evaluation_run_repository import EvaluationRunRepository
from ai_governance.settings import Settings

logger = logging.getLogger(__name__)


class EvaluationRunRepositoryFactory:
    """Selects the concrete EvaluationRunRepository implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> EvaluationRunRepository:
        backend = self._settings.evaluation_run_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory evaluation run repository")
                from ai_governance.repositories.in_memory_evaluation_run_repository import (
                    InMemoryEvaluationRunRepository,
                )

                return InMemoryEvaluationRunRepository()

            case "sqlite":
                path = self._settings.evaluation_run_sqlite_path
                if not path:
                    raise ValueError(
                        "AI_GOVERNANCE_EVALUATION_RUN_SQLITE_PATH is required when "
                        "AI_GOVERNANCE_EVALUATION_RUN_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite evaluation run repository: %s", path)
                from ai_governance.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )
                from ai_governance.repositories.sqlite.sqlite_evaluation_run_repository import (
                    SQLiteEvaluationRunRepository,
                )

                return SQLiteEvaluationRunRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.evaluation_run_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_EVALUATION_RUN_POSTGRES_DSN is required when "
                        "AI_GOVERNANCE_EVALUATION_RUN_REPOSITORY=postgres"
                    )
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres import (
                    PostgresEvaluationRunRepository,
                )

                return PostgresEvaluationRunRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported evaluation run repository backend: {unknown}"
                )
