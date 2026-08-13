"""
Evaluation service wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.providers import get_provider_registry
from ai_governance.api.dependencies.provider_installations import get_provider_installation_service
from ai_governance.api.dependencies.repositories import get_evaluation_repository
from ai_governance.api.dependencies.ontology import get_ontology_sync_event_publisher
from ai_governance.api.dependencies.settings_control import get_configuration_service
from ai_governance.api.dependencies.telemetry import get_telemetry_service


def get_evaluation_service(
    provider_registry: Any = Depends(get_provider_registry),
) -> Any:
    """
    Create an EvaluationService through FastAPI dependency injection.
    """

    from ai_governance.evaluation import EvaluationService

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

    from ai_governance.services.history import EvaluationHistoryService

    return EvaluationHistoryService(
        evaluation_repository, configuration_service=configuration_service
    )


def get_evaluation_api_service(
    provider_registry: Any = Depends(get_provider_registry),
    evaluation_repository: Any = Depends(get_evaluation_repository),
    ontology_event_publisher: Any = Depends(get_ontology_sync_event_publisher),
    configuration_service: Any = Depends(get_configuration_service),
    provider_installation_service: Any = Depends(get_provider_installation_service),
    telemetry_collector: Any = Depends(get_telemetry_service),
) -> Any:
    """
    Create the REST evaluation facade through dependency injection.
    """

    from ai_governance.services.evaluation_api_service import EvaluationApiService

    return EvaluationApiService(
        provider_registry=provider_registry,
        evaluation_repository=evaluation_repository,
        ontology_event_publisher=ontology_event_publisher,
        configuration_service=configuration_service,
        provider_installation_service=provider_installation_service,
        telemetry_collector=telemetry_collector,
    )
