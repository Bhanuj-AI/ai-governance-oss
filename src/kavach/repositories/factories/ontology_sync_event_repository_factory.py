"""Factory for OntologySyncEventRepository."""

from __future__ import annotations

import logging

from kavach.ontology.synchronization.events import OntologySyncEventRepository
from kavach.settings import Settings

logger = logging.getLogger(__name__)


class OntologySyncEventRepositoryFactory:
    """Selects the concrete OntologySyncEventRepository implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> OntologySyncEventRepository:
        backend = self._settings.ontology_sync_event_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory ontology sync event repository")
                from kavach.repositories import InMemoryOntologySyncEventRepository

                return InMemoryOntologySyncEventRepository()

            case "sqlite":
                path = self._settings.ontology_sync_event_sqlite_path
                if not path:
                    raise ValueError(
                        "KAVACH_ONTOLOGY_SYNC_EVENT_SQLITE_PATH is required when "
                        "KAVACH_ONTOLOGY_SYNC_EVENT_REPOSITORY=sqlite"
                    )
                logger.debug(
                    "Selected SQLite ontology sync event repository: %s", path
                )
                from kavach.repositories.sqlite import (
                    SQLiteOntologySyncEventRepository,
                )
                from kavach.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLiteOntologySyncEventRepository(
                    create_sqlite_database(path)
                )

            case "postgres":
                dsn = self._settings.ontology_sync_event_postgres_dsn
                if not dsn:
                    raise ValueError(
                        "KAVACH_ONTOLOGY_SYNC_EVENT_POSTGRES_DSN is required when "
                        "KAVACH_ONTOLOGY_SYNC_EVENT_REPOSITORY=postgres"
                    )
                from kavach.databases.postgres.database import PostgresDatabase
                from kavach.repositories.postgres import PostgresOntologySyncEventRepository

                database = PostgresDatabase(dsn)
                database.initialize()
                return PostgresOntologySyncEventRepository(database)

            case unknown:
                raise ValueError(
                    f"Unsupported ontology sync event repository backend: {unknown}"
                )
