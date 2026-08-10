from __future__ import annotations

from pathlib import Path

from ai_governance.settings import Settings


class ReplayResultRepositoryFactory:
    """Uses the Replay persistence backend for immutable ReplayResult evidence."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self):
        match self._settings.replay_repository:
            case "inmemory" | "memory":
                from ai_governance.repositories.in_memory_replay_result_repository import (
                    InMemoryReplayResultRepository,
                )

                return InMemoryReplayResultRepository()
            case "sqlite":
                from ai_governance.databases.sqlite.database import SQLiteDatabase
                from ai_governance.repositories.sqlite.sqlite_replay_result_repository import (
                    SQLiteReplayResultRepository,
                )

                if not self._settings.replay_sqlite_path:
                    raise ValueError(
                        "AI_GOVERNANCE_REPLAY_SQLITE_PATH is required for SQLite ReplayResult storage."
                    )
                database = SQLiteDatabase(Path(self._settings.replay_sqlite_path))
                database.initialize()
                return SQLiteReplayResultRepository(database)
            case "postgres":
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres.postgres_replay_result_repository import (
                    PostgresReplayResultRepository,
                )

                if not self._settings.replay_postgres_dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_REPLAY_POSTGRES_DSN is required for PostgreSQL ReplayResult storage."
                    )
                database = PostgresDatabase(self._settings.replay_postgres_dsn)
                database.initialize()
                return PostgresReplayResultRepository(database)
            case backend:
                raise ValueError(
                    f"Unsupported replay result repository backend: {backend}"
                )
