"""
Prompt / model / dataset registry service wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.events import get_event_publisher
from ai_governance.api.dependencies.ontology import get_ontology_sync_event_publisher
from ai_governance.api.dependencies.providers import get_provider_registry
from ai_governance.api.dependencies.repositories import (
    get_dataset_repository,
    get_model_repository,
    get_prompt_repository,
)
from ai_governance.api.dependencies.settings_control import get_configuration_service
from ai_governance.events import EventPublisher
from ai_governance.settings_control import ConfigurationService
from ai_governance.settings_control.domain import SettingContext
from ai_governance.tenancy.domain import TenantContext


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
    configuration_service: ConfigurationService = Depends(get_configuration_service),
) -> Any:
    """
    Create a model registry service through FastAPI dependency injection.
    """

    from ai_governance.services.models import ModelRegistryService

    def allowed_runtime_providers(context: TenantContext) -> tuple[str, ...]:
        value = configuration_service.get(
            "model_registry.allowed_runtime_providers",
            SettingContext(context.organization_id, context.project_id),
        )
        return tuple(value)

    return ModelRegistryService(
        model_repository,
        ontology_event_publisher=ontology_event_publisher,
        event_publisher=event_publisher,
        allowed_runtime_providers=allowed_runtime_providers,
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
