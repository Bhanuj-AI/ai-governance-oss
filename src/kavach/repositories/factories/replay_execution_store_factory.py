"""Backend selection for immutable Replay execution evidence."""

from __future__ import annotations

from pathlib import Path

from kavach.settings import Settings


class ReplayExecutionStoreFactory:
    """Select one shared source store for API and worker processes."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self):
        match self._settings.replay_execution_catalog_backend:
            case "inmemory":
                from kavach.services.replay_execution_discovery import (
                    InMemoryReplaySourceResolver,
                )

                return InMemoryReplaySourceResolver()
            case "sqlite":
                if not self._settings.replay_execution_catalog_sqlite_path:
                    raise ValueError(
                        "KAVACH_REPLAY_EXECUTION_CATALOG_SQLITE_PATH is required "
                        "when the replay execution backend is sqlite"
                    )
                from kavach.databases.sqlite.database import SQLiteDatabase
                from kavach.repositories.sqlite.sqlite_replay_execution_store import (
                    SQLiteReplayExecutionStore,
                )

                database = SQLiteDatabase(
                    Path(self._settings.replay_execution_catalog_sqlite_path)
                )
                database.initialize()
                return SQLiteReplayExecutionStore(database)
            case "postgres":
                if not self._settings.replay_postgres_dsn:
                    raise ValueError(
                        "KAVACH_REPLAY_POSTGRES_DSN is required when the replay "
                        "execution backend is postgres"
                    )
                from kavach.databases.postgres.database import PostgresDatabase
                from kavach.repositories.postgres.postgres_replay_execution_store import (
                    PostgresReplayExecutionStore,
                )

                database = PostgresDatabase(self._settings.replay_postgres_dsn)
                database.initialize()
                return PostgresReplayExecutionStore(database)
            case backend:
                raise ValueError(f"Unsupported replay execution backend: {backend}")
