"""Select evidence-fidelity persistence with the Agent Runtime evidence store."""

from __future__ import annotations

from ai_governance.settings import Settings


class EvidenceFidelityComparisonRepositoryFactory:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self):
        if self._settings.agent_execution_repository == "inmemory":
            from ai_governance.repositories.in_memory.in_memory_evidence_fidelity_repository import (
                InMemoryEvidenceFidelityComparisonRepository,
            )
            return InMemoryEvidenceFidelityComparisonRepository()
        if self._settings.agent_execution_repository == "sqlite":
            from pathlib import Path

            from ai_governance.databases.sqlite.database import SQLiteDatabase
            from ai_governance.repositories.sqlite.sqlite_evidence_fidelity_repository import (
                SQLiteEvidenceFidelityComparisonRepository,
            )
            database = SQLiteDatabase(Path(self._settings.agent_execution_sqlite_path or ""))
            database.initialize()
            return SQLiteEvidenceFidelityComparisonRepository(database)
        if self._settings.agent_execution_repository == "postgres":
            from ai_governance.databases.postgres.database import PostgresDatabase
            from ai_governance.repositories.postgres.postgres_evidence_fidelity_repository import (
                PostgresEvidenceFidelityComparisonRepository,
            )
            database = PostgresDatabase(self._settings.agent_execution_postgres_dsn or "")
            database.initialize()
            return PostgresEvidenceFidelityComparisonRepository(database)
        raise ValueError(f"Unsupported evidence-fidelity backend: {self._settings.agent_execution_repository}")
