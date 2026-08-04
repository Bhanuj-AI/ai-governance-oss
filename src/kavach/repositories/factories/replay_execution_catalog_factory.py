from __future__ import annotations

from pathlib import Path

from kavach.services.replay_execution_discovery import (
    InMemoryReplayExecutionCatalog,
    ReplayExecutionCatalog,
)
from kavach.settings import Settings


class ReplayExecutionCatalogFactory:
    """Select a durable discovery projection without production fallback."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> ReplayExecutionCatalog:
        match self._settings.replay_execution_catalog_backend:
            case "inmemory":
                return InMemoryReplayExecutionCatalog()
            case "sqlite":
                if not self._settings.replay_execution_catalog_sqlite_path:
                    raise ValueError(
                        "KAVACH_REPLAY_EXECUTION_CATALOG_SQLITE_PATH is required when the catalog backend is sqlite"
                    )
                from kavach.databases.sqlite.database import SQLiteDatabase
                from kavach.repositories.sqlite.sqlite_replay_execution_catalog import (
                    SQLiteReplayExecutionCatalog,
                )

                database = SQLiteDatabase(
                    Path(self._settings.replay_execution_catalog_sqlite_path)
                )
                database.initialize()
                return SQLiteReplayExecutionCatalog(database)
            case "postgres":
                if not self._settings.replay_postgres_dsn:
                    raise ValueError(
                        "KAVACH_REPLAY_POSTGRES_DSN is required when the catalog backend is postgres"
                    )
                from kavach.databases.postgres.database import PostgresDatabase
                from kavach.repositories.postgres.postgres_replay_execution_catalog import (
                    PostgresReplayExecutionCatalog,
                )

                database = PostgresDatabase(self._settings.replay_postgres_dsn)
                database.initialize()
                return PostgresReplayExecutionCatalog(database)
            case backend:
                raise ValueError(
                    f"Unsupported replay execution catalog backend: {backend}"
                )
