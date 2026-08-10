"""Factory for GovernanceDecisionRepository."""

from __future__ import annotations

import logging
from typing import Any

from ai_governance.repositories.governance_decision_repository import (
    GovernanceDecisionRepository,
)
from ai_governance.settings import Settings

logger = logging.getLogger(__name__)


class GovernanceDecisionRepositoryFactory:
    """Selects the concrete GovernanceDecisionRepository implementation.

    Some repositories require runtime collaborators (e.g. an ontology event
    publisher).  These are passed explicitly via ``create()`` rather than
    being looked up inside the factory to avoid hidden dependencies on
    FastAPI dependency modules.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(
        self,
        *,
        ontology_event_publisher: Any | None = None,
    ) -> GovernanceDecisionRepository:
        backend = self._settings.governance_decision_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory governance decision repository")
                from ai_governance.repositories import InMemoryGovernanceDecisionRepository

                return InMemoryGovernanceDecisionRepository(
                    ontology_event_publisher=ontology_event_publisher,
                )

            case "sqlite":
                path = self._settings.governance_decision_sqlite_path
                if not path:
                    raise ValueError(
                        "AI_GOVERNANCE_GOVERNANCE_DECISION_SQLITE_PATH is required when "
                        "AI_GOVERNANCE_GOVERNANCE_DECISION_REPOSITORY=sqlite"
                    )
                logger.debug(
                    "Selected SQLite governance decision repository: %s", path
                )
                from ai_governance.repositories.sqlite import (
                    SQLiteGovernanceDecisionRepository,
                )
                from ai_governance.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLiteGovernanceDecisionRepository(
                    create_sqlite_database(path),
                    ontology_event_publisher=ontology_event_publisher,
                )

            case "postgres":
                dsn = self._settings.governance_decision_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "AI_GOVERNANCE_GOVERNANCE_DECISION_POSTGRES_DSN is required when "
                        "AI_GOVERNANCE_GOVERNANCE_DECISION_REPOSITORY=postgres"
                    )
                from ai_governance.databases.postgres.database import PostgresDatabase
                from ai_governance.repositories.postgres import PostgresGovernanceDecisionRepository

                return PostgresGovernanceDecisionRepository(
                    PostgresDatabase(dsn),
                    ontology_event_publisher=ontology_event_publisher,
                )

            case unknown:
                raise ValueError(
                    f"Unsupported governance decision repository backend: {unknown}"
                )
