"""Select intervention-policy persistence alongside Agents Runtime evidence."""

from __future__ import annotations

from ai_governance.settings import Settings


class EvidenceInterventionPolicyRepositoryFactory:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self):
        if self._settings.agent_execution_repository == "inmemory":
            from ai_governance.repositories.in_memory.in_memory_evidence_intervention_policy_repository import (
                InMemoryEvidenceInterventionPolicyRepository,
            )

            return InMemoryEvidenceInterventionPolicyRepository()
        if self._settings.agent_execution_repository == "sqlite":
            from pathlib import Path

            from ai_governance.databases.sqlite.database import SQLiteDatabase
            from ai_governance.repositories.sqlite.sqlite_evidence_intervention_policy_repository import (
                SQLiteEvidenceInterventionPolicyRepository,
            )

            database = SQLiteDatabase(
                Path(self._settings.agent_execution_sqlite_path or "")
            )
            database.initialize()
            return SQLiteEvidenceInterventionPolicyRepository(database)
        if self._settings.agent_execution_repository == "postgres":
            from ai_governance.databases.postgres.database import PostgresDatabase
            from ai_governance.repositories.postgres.postgres_evidence_intervention_policy_repository import (
                PostgresEvidenceInterventionPolicyRepository,
            )

            database = PostgresDatabase(
                self._settings.agent_execution_postgres_dsn or ""
            )
            database.initialize()
            return PostgresEvidenceInterventionPolicyRepository(database)
        raise ValueError(
            f"Unsupported intervention policy backend: {self._settings.agent_execution_repository}"
        )
