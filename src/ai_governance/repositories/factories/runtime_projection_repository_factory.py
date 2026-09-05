"""Backend selection for runtime ontology projection state repositories.

Projection state is persisted in the same durable store as agent execution
data (inmemory, sqlite, or postgres) so it survives Neo4j outages and
process restarts.
"""

from __future__ import annotations

from pathlib import Path

from ai_governance.settings import Settings


class RuntimeProjectionRepositoryFactory:
    """Select concrete runtime projection state repositories."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self):
        match self._settings.agent_execution_repository:
            case "inmemory":
                from ai_governance.repositories.in_memory.in_memory_projection_repository import (
                    InMemoryProjectionRepository,
                )

                return InMemoryProjectionRepository()
            case "sqlite":
                if not self._settings.agent_execution_sqlite_path:
                    raise ValueError(
                        "AI_GOVERNANCE_AGENT_EXECUTION_SQLITE_PATH is required "
                        "when the agent execution backend is sqlite"
                    )
                from ai_governance.databases.sqlite.database import SQLiteDatabase
                from ai_governance.repositories.sqlite.sqlite_runtime_projection_repository import (
                    SQLiteRuntimeProjectionRepository,
                )

                database = SQLiteDatabase(
                    Path(self._settings.agent_execution_sqlite_path)
                )
                database.initialize()
                return SQLiteRuntimeProjectionRepository(database)
            case "postgres":
                if not self._settings.agent_execution_postgres_dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_AGENT_EXECUTION_POSTGRES_DSN is required "
                        "when the agent execution backend is postgres"
                    )
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres.postgres_runtime_projection_repository import (
                    PostgresRuntimeProjectionRepository,
                )

                database = PostgresDatabase(self._settings.agent_execution_postgres_dsn)
                database.initialize()
                return PostgresRuntimeProjectionRepository(database)
            case backend:
                raise ValueError(f"Unsupported runtime projection backend: {backend}")
