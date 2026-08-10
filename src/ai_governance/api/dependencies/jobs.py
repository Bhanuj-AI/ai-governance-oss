"""
Job wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.repositories import get_job_repository
from ai_governance.api.dependencies.ontology import get_ontology_sync_event_publisher
from ai_governance.api.dependencies.settings_control import get_configuration_service
from ai_governance.api.dependencies.events import get_event_publisher
from ai_governance.events import EventPublisher


def get_job_api_service(
    job_repository: Any = Depends(get_job_repository),
    ontology_event_publisher: Any = Depends(get_ontology_sync_event_publisher),
    configuration_service: Any = Depends(get_configuration_service),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> Any:
    """
    Create the REST job facade through dependency injection.
    """

    from ai_governance.services import JobApiService

    return JobApiService(
        job_repository,
        ontology_event_publisher=ontology_event_publisher,
        configuration_service=configuration_service,
        event_publisher=event_publisher,
    )
