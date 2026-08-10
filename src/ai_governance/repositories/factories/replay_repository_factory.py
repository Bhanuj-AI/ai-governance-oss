from __future__ import annotations

from pathlib import Path

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.repositories.replay_repository import ReplayRepository
from ai_governance.settings import Settings


class ReplayRepositoryFactory:
    """Select the configured Replay repository without fallback."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> ReplayRepository:
        match self._settings.replay_repository:
            case "inmemory" | "memory":
                from ai_governance.repositories.in_memory_replay_repository import (
                    InMemoryReplayRepository,
                )

                return InMemoryReplayRepository()
            case "sqlite":
                if not self._settings.replay_sqlite_path:
                    raise ValueError(
                        "AI_GOVERNANCE_REPLAY_SQLITE_PATH is required when "
                        "AI_GOVERNANCE_REPLAY_REPOSITORY=sqlite"
                    )
                from ai_governance.databases.sqlite.database import SQLiteDatabase
                from ai_governance.repositories.sqlite.sqlite_replay_repository import (
                    SQLiteReplayRepository,
                )

                database = SQLiteDatabase(Path(self._settings.replay_sqlite_path))
                database.initialize()
                return SQLiteReplayRepository(database)
            case "postgres":
                if not self._settings.replay_postgres_dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_REPLAY_POSTGRES_DSN is required when "
                        "AI_GOVERNANCE_REPLAY_REPOSITORY=postgres"
                    )
                from ai_governance.repositories.postgres.postgres_replay_repository import (
                    PostgresReplayRepository,
                )

                database = PostgresDatabase(self._settings.replay_postgres_dsn)
                database.initialize()
                return PostgresReplayRepository(database)
            case backend:
                raise ValueError(f"Unsupported replay repository backend: {backend}")
