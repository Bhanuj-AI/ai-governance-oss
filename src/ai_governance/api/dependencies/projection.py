"""Dependency providers for ontology projection endpoints.

Repository construction is isolated here so router modules never import
from ``ai_governance.repositories``.
"""

from __future__ import annotations

from functools import lru_cache

from ai_governance.services.ontology_projection_service import (
    OntologyProjectionService,
)


@lru_cache(maxsize=1)
def get_ontology_projection_service() -> OntologyProjectionService:
    """Build and return the ontology projection service.

    Repository construction is delegated to this provider so router
    modules remain repository-free. The durable projection repository
    (PostgreSQL/SQLite) persists state outside Neo4j so it survives
    graph outages and process restarts.
    """
    from ai_governance.api.dependencies.agent_execution import (
        get_agent_execution_service,
    )
    from ai_governance.repositories.factories import (
        RuntimeProjectionRepositoryFactory,
    )
    from ai_governance.settings import load_settings

    service = get_agent_execution_service()
    settings = load_settings()

    # Build the durable projection state repository.
    durable_repo = RuntimeProjectionRepositoryFactory(settings).create()

    # Build the Neo4j graph projection repository, wired to the durable repo.
    from ai_governance.repositories.neo4j_projection_repository import (
        Neo4jProjectionRepository,
    )

    projection_repo = Neo4jProjectionRepository.from_environment(
        durable_projection_repo=durable_repo,
    )
    return OntologyProjectionService(
        service._execution_repo,
        service._event_repo,
        projection_repo,
    )
