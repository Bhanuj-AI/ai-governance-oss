"""Backend selection for immutable runtime-action delegation storage."""

from __future__ import annotations

from pathlib import Path

from ai_governance.settings import Settings


class RuntimeActionDelegationRepositoryFactory:
    """Use the configured agent-execution backend for delegation evidence."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self):
        match self._settings.agent_execution_repository:
            case "inmemory":
                from ai_governance.repositories.in_memory.in_memory_runtime_action_delegation_repository import (
                    InMemoryRuntimeActionDelegationRepository,
                )

                return InMemoryRuntimeActionDelegationRepository()
            case "sqlite":
                if not self._settings.agent_execution_sqlite_path:
                    raise ValueError(
                        "AI_GOVERNANCE_AGENT_EXECUTION_SQLITE_PATH is required "
                        "when the agent execution backend is sqlite"
                    )
                from ai_governance.databases.sqlite.database import SQLiteDatabase
                from ai_governance.repositories.sqlite.sqlite_runtime_action_delegation_repository import (
                    SQLiteRuntimeActionDelegationRepository,
                )

                database = SQLiteDatabase(
                    Path(self._settings.agent_execution_sqlite_path)
                )
                database.initialize()
                return SQLiteRuntimeActionDelegationRepository(database)
            case "postgres":
                if not self._settings.agent_execution_postgres_dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_AGENT_EXECUTION_POSTGRES_DSN is required "
                        "when the agent execution backend is postgres"
                    )
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres.postgres_runtime_action_delegation_repository import (
                    PostgresRuntimeActionDelegationRepository,
                )

                database = PostgresDatabase(self._settings.agent_execution_postgres_dsn)
                database.initialize()
                return PostgresRuntimeActionDelegationRepository(database)
            case backend:
                raise ValueError(f"Unsupported agent execution backend: {backend}")
