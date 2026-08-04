"""Factory for OntologyGraphRepository."""

from __future__ import annotations

import logging

from kavach.ontology.repositories import OntologyGraphRepository
from kavach.settings import Settings

logger = logging.getLogger(__name__)


class OntologyGraphRepositoryFactory:
    """Selects the concrete OntologyGraphRepository implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> OntologyGraphRepository:
        backend = self._settings.ontology_repository

        match backend:
            case "inmemory":
                logger.debug("Selected in-memory ontology graph repository")
                from kavach.ontology import InMemoryOntologyGraphRepository

                return InMemoryOntologyGraphRepository()

            case "neo4j":
                logger.info("Selected Neo4j ontology graph repository")
                from kavach.ontology.neo4j_repository import (
                    Neo4jOntologyGraphRepository,
                )

                return Neo4jOntologyGraphRepository.from_environment()

            case "sqlite":
                raise ValueError(
                    "KAVACH_ONTOLOGY_REPOSITORY=sqlite is configured, "
                    "but SQLiteOntologyGraphRepository is not implemented"
                )

            case "postgres":
                raise ValueError(
                    "KAVACH_ONTOLOGY_REPOSITORY=postgres is configured, "
                    "but PostgresOntologyGraphRepository is not implemented"
                )

            case unknown:
                raise ValueError(
                    f"Unsupported ontology graph repository backend: {unknown}"
                )
