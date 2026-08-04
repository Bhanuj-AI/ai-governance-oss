"""Factory for LeaderboardRepository."""

from __future__ import annotations

import logging

from kavach.repositories.leaderboard_repository import LeaderboardRepository
from kavach.settings import Settings

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
                from kavach.repositories.in_memory_leaderboard_repository import (
                    InMemoryLeaderboardRepository,
                )

                return InMemoryLeaderboardRepository()

            case "sqlite":
                path = self._settings.leaderboard_sqlite_path
                if not path:
                    raise ValueError(
                        "KAVACH_LEADERBOARD_SQLITE_PATH is required when "
                        "KAVACH_LEADERBOARD_REPOSITORY=sqlite"
                    )
                logger.debug("Selected SQLite leaderboard repository: %s", path)
                from kavach.repositories.sqlite.sqlite_leaderboard_repository import SQLiteLeaderboardRepository

                from kavach.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLiteLeaderboardRepository(create_sqlite_database(path))

            case "postgres":
                dsn = self._settings.leaderboard_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "KAVACH_LEADERBOARD_POSTGRES_DSN is required when "
                        "KAVACH_LEADERBOARD_REPOSITORY=postgres"
                    )
                from kavach.databases.postgres.database import PostgresDatabase
                from kavach.repositories.postgres import PostgresLeaderboardRepository

                return PostgresLeaderboardRepository(PostgresDatabase(dsn))

            case unknown:
                raise ValueError(
                    f"Unsupported leaderboard repository backend: {unknown}"
                )
