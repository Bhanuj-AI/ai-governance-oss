"""Factory for LeaderboardRepository."""

from __future__ import annotations

import logging

from ai_governance.repositories.leaderboard_repository import LeaderboardRepository
from ai_governance.settings import Settings

logger = logging.getLogger(__name__)


class LeaderboardRepositoryFactory:
    """Selects the concrete LeaderboardRepository implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> LeaderboardRepository:
        backend = self._settings.leaderboard_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory leaderboard repository")
                from ai_governance.repositories.in_memory_leaderboard_repository import (
                    InMemoryLeaderboardRepository,
                )

                return InMemoryLeaderboardRepository()

            case "sqlite":
                path = self._settings.leaderboard_sqlite_path
                if not path:
                    raise ValueError(
                        "AI_GOVERNANCE_LEADERBOARD_SQLITE_PATH is required when "
                        "AI_GOVERNANCE_LEADERBOARD_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite leaderboard repository: %s", path)
                from ai_governance.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )
                from ai_governance.repositories.sqlite.sqlite_leaderboard_repository import (
                    SQLiteLeaderboardRepository,
                )

                return SQLiteLeaderboardRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.leaderboard_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_LEADERBOARD_POSTGRES_DSN is required when "
                        "AI_GOVERNANCE_LEADERBOARD_REPOSITORY=postgres"
                    )
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres import (
                    PostgresLeaderboardRepository,
                )

                return PostgresLeaderboardRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported leaderboard repository backend: {unknown}"
                )
