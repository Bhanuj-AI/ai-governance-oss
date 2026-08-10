"""
Prompt / model / dataset registry service wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.providers import get_provider_registry
from ai_governance.api.dependencies.repositories import (
    get_dataset_repository,
    get_model_repository,
    get_prompt_repository,
)
from ai_governance.api.dependencies.ontology import get_ontology_sync_event_publisher
from ai_governance.api.dependencies.events import get_event_publisher
from ai_governance.events import EventPublisher


def get_provider_registry_service(
    provider_registry: Any = Depends(get_provider_registry),
) -> Any:
    """
    Create a provider registry service through FastAPI dependency injection.
    """

    from ai_governance.services.provider_registry_service import (
        ProviderRegistryService,
    )

    return ProviderRegistryService(provider_registry)


def get_prompt_registry_service(
    prompt_repository: Any = Depends(get_prompt_repository),
    ontology_event_publisher: Any = Depends(get_ontology_sync_event_publisher),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> Any:
    """
    Create a prompt registry service for dependency wiring checks.
    """

    from ai_governance.services.prompts import PromptRegistryService

    return PromptRegistryService(
        prompt_repository,
        ontology_event_publisher=ontology_event_publisher,
        event_publisher=event_publisher,
    )


def get_model_registry_service(
    model_repository: Any = Depends(get_model_repository),
    ontology_event_publisher: Any = Depends(get_ontology_sync_event_publisher),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> Any:
    """
    Create a model registry service through FastAPI dependency injection.
    """

    from ai_governance.services.models import ModelRegistryService

    return ModelRegistryService(
        model_repository,
        ontology_event_publisher=ontology_event_publisher,
        event_publisher=event_publisher,
    )


def get_dataset_registry_service(
    dataset_repository: Any = Depends(get_dataset_repository),
    ontology_event_publisher: Any = Depends(get_ontology_sync_event_publisher),
) -> Any:
    """
    Create a dataset registry service through FastAPI dependency injection.
    """

    from ai_governance.services.datasets import DatasetRegistryService

    return DatasetRegistryService(
        dataset_repository,
        ontology_event_publisher=ontology_event_publisher,
    )
