from __future__ import annotations

from ai_governance.providers import EvaluationProviderRegistry
from ai_governance.providers.provider_descriptor import (
    ProviderDescriptor,
    normalize_provider_name,
)


class ProviderRegistryService:
    """
    Application service for read-only provider registry discovery.
    """

    def __init__(
        self,
        provider_registry: EvaluationProviderRegistry,
    ) -> None:
        self._provider_registry = provider_registry

    def list_providers(self) -> list[ProviderDescriptor]:
        """
        Return descriptors for every registered evaluation provider.
        """

        return self._provider_registry.list()

    def get_provider(
        self,
        provider_name: str,
    ) -> ProviderDescriptor:
        """
        Return one provider descriptor by normalized provider name.
        """

        normalized_name = normalize_provider_name(provider_name)
        return self._provider_registry.get(normalized_name).descriptor
