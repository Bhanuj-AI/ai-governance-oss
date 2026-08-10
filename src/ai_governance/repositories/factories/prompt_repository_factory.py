"""Factory for PromptRepository."""

from __future__ import annotations

import logging

from ai_governance.repositories.prompt_repository import PromptRepository
from ai_governance.settings import Settings

logger = logging.getLogger(__name__)


class PromptRepositoryFactory:
    """Selects the concrete PromptRepository implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> PromptRepository:
        backend = self._settings.prompt_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory prompt repository")
                from ai_governance.repositories.in_memory_prompt_repository import (
                    InMemoryPromptRepository,
                )

                return InMemoryPromptRepository()

            case "sqlite":
                path = self._settings.prompt_sqlite_path
                if not path:
                    raise ValueError(
                        "AI_GOVERNANCE_PROMPT_SQLITE_PATH is required when "
                        "AI_GOVERNANCE_PROMPT_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite prompt repository: %s", path)
                from ai_governance.repositories.sqlite.sqlite_prompt_repository import SQLitePromptRepository

                from ai_governance.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLitePromptRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.prompt_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_PROMPT_POSTGRES_DSN is required when "
                        "AI_GOVERNANCE_PROMPT_REPOSITORY=postgres"
                    )
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres import PostgresPromptRepository

                return PostgresPromptRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported prompt repository backend: {unknown}"
                )
