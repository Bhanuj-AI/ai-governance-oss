"""
Ontology wiring for the Kavach platform.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import Depends

from kavach.api.dependencies.repositories import (
    get_ontology_graph_query_repository,
    get_ontology_sync_event_repository,
)


@lru_cache(maxsize=1)
def get_ontology_sync_event_publisher() -> Any:
    """
    Create a durable ontology synchronization event publisher.
    """

    from kavach.ontology.synchronization import OntologySyncEventPublisher

    return OntologySyncEventPublisher(
        get_ontology_sync_event_repository(),
    )


def get_ontology_graph_query_service(
    query_repository: Any = Depends(get_ontology_graph_query_repository),
) -> Any:
    """
    Create the ontology graph query service.
    """

    from kavach.ontology import OntologyGraphQueryService

    return OntologyGraphQueryService(query_repository)


def get_ontology_sync_event_service(
    event_repository: Any = Depends(get_ontology_sync_event_repository),
) -> Any:
    """
    Create the ontology synchronization event status facade.
    """

    from kavach.ontology.synchronization import OntologySyncEventService

    return OntologySyncEventService(event_repository)
