"""
Evaluation service wiring for the Kavach platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from kavach.api.dependencies.providers import get_provider_registry
from kavach.api.dependencies.provider_installations import get_provider_installation_service
from kavach.api.dependencies.repositories import get_evaluation_repository
from kavach.api.dependencies.ontology import get_ontology_sync_event_publisher
from kavach.api.dependencies.settings_control import get_configuration_service


def get_evaluation_service(
    provider_registry: Any = Depends(get_provider_registry),
) -> Any:
    """
    Create an EvaluationService through FastAPI dependency injection.
    """

    from kavach.evaluation import EvaluationService

    return EvaluationService(
        provider_registry=provider_registry,
        provider_name="trulens",
    )


def get_evaluation_history_service(
    evaluation_repository: Any = Depends(get_evaluation_repository),
    configuration_service: Any = Depends(get_configuration_service),
) -> Any:
    """
    Create an EvaluationHistoryService through dependency injection.
    """

    from kavach.services.history import EvaluationHistoryService

    return EvaluationHistoryService(
        evaluation_repository, configuration_service=configuration_service
    )


def get_evaluation_api_service(
    provider_registry: Any = Depends(get_provider_registry),
    evaluation_repository: Any = Depends(get_evaluation_repository),
    ontology_event_publisher: Any = Depends(get_ontology_sync_event_publisher),
    configuration_service: Any = Depends(get_configuration_service),
    provider_installation_service: Any = Depends(get_provider_installation_service),
) -> Any:
    """
    Create the REST evaluation facade through dependency injection.
    """

    from kavach.services.evaluation_api_service import EvaluationApiService

    return EvaluationApiService(
        provider_registry=provider_registry,
        evaluation_repository=evaluation_repository,
        ontology_event_publisher=ontology_event_publisher,
        configuration_service=configuration_service,
        provider_installation_service=provider_installation_service,
    )
