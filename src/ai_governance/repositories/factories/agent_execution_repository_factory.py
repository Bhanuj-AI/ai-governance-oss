"""Backend selection for agent execution trace repositories."""

from __future__ import annotations

from pathlib import Path

from ai_governance.settings import Settings


class AgentExecutionRepositoryFactory:
    """Select concrete AgentExecution and AgentExecutionEvent repositories."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self):
        match self._settings.agent_execution_repository:
            case "inmemory":
                from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
                    InMemoryAgentExecutionEventRepository,
                    InMemoryAgentExecutionRepository,
                )

                return _AgentExecutionRepositories(
                    execution=InMemoryAgentExecutionRepository(),
                    event=InMemoryAgentExecutionEventRepository(),
                )
            case "sqlite":
                if not self._settings.agent_execution_sqlite_path:
                    raise ValueError(
                        "AI_GOVERNANCE_AGENT_EXECUTION_SQLITE_PATH is required "
                        "when the agent execution backend is sqlite"
                    )
                from ai_governance.databases.sqlite.database import SQLiteDatabase
                from ai_governance.repositories.sqlite.sqlite_agent_execution_repository import (
                    SQLiteAgentExecutionEventRepository,
                    SQLiteAgentExecutionRepository,
                )

                database = SQLiteDatabase(
                    Path(self._settings.agent_execution_sqlite_path)
                )
                database.initialize()
                return _AgentExecutionRepositories(
                    execution=SQLiteAgentExecutionRepository(database),
                    event=SQLiteAgentExecutionEventRepository(database),
                )
            case "postgres":
                if not self._settings.agent_execution_postgres_dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_AGENT_EXECUTION_POSTGRES_DSN is required "
                        "when the agent execution backend is postgres"
                    )
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres.postgres_agent_execution_repository import (
                    PostgresAgentExecutionEventRepository,
                    PostgresAgentExecutionRepository,
                )

                database = PostgresDatabase(self._settings.agent_execution_postgres_dsn)
                database.initialize()
                return _AgentExecutionRepositories(
                    execution=PostgresAgentExecutionRepository(database),
                    event=PostgresAgentExecutionEventRepository(database),
                )
            case backend:
                raise ValueError(f"Unsupported agent execution backend: {backend}")


class _AgentExecutionRepositories:
    """Container holding both execution and event repositories."""

    def __init__(
        self,
        execution: object,
        event: object,
    ) -> None:
        self.execution = execution
        self.event = event
