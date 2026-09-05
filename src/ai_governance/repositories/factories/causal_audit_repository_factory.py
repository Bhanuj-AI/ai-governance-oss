"""Select causal-audit persistence alongside Agents Runtime evidence."""

from __future__ import annotations

from ai_governance.settings import Settings


class CausalAuditRepositoryFactory:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self):
        # Audits deliberately share the execution evidence backend.  A separate
        # store would weaken the immutable execution→audit lineage.
        if self._settings.agent_execution_repository == "inmemory":
            from ai_governance.repositories.in_memory.in_memory_causal_audit_repository import (
                InMemoryCausalAuditRepository,
            )

            return InMemoryCausalAuditRepository()
        if self._settings.agent_execution_repository == "sqlite":
            from pathlib import Path

            from ai_governance.databases.sqlite.database import SQLiteDatabase
            from ai_governance.repositories.sqlite.sqlite_causal_audit_repository import (
                SQLiteCausalAuditRepository,
            )

            database = SQLiteDatabase(
                Path(self._settings.agent_execution_sqlite_path or "")
            )
            database.initialize()
            return SQLiteCausalAuditRepository(database)
        if self._settings.agent_execution_repository == "postgres":
            from ai_governance.databases.postgres.database import PostgresDatabase
            from ai_governance.repositories.postgres.postgres_causal_audit_repository import (
                PostgresCausalAuditRepository,
            )

            database = PostgresDatabase(
                self._settings.agent_execution_postgres_dsn or ""
            )
            database.initialize()
            return PostgresCausalAuditRepository(database)
        raise ValueError(
            f"Unsupported causal audit backend: {self._settings.agent_execution_repository}"
        )
