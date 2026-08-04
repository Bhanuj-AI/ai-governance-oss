from __future__ import annotations

from kavach.providers.errors import (
    ProviderAlreadyRegisteredError,
    ProviderNotFoundError,
)
from kavach.providers.evaluation_provider import EvaluationProvider
from kavach.providers.provider_descriptor import (
    ProviderDescriptor,
    normalize_provider_name,
)


class EvaluationProviderRegistry:
    """
    In-process registry for evaluation provider adapters.

    The registry lets application code resolve providers by normalized name
    without importing concrete provider implementations in orchestration
    layers. Register adapters during application startup, then inject the
    registry and desired provider name into EvaluationService.

    Example:
        registry = EvaluationProviderRegistry()
        registry.register(example_provider)

        service = EvaluationService(
            provider_registry=registry,
            provider_name="example_provider",
        )
    """

    def __init__(self) -> None:
        self._providers: dict[str, EvaluationProvider] = {}

    def register(
        self,
        provider: EvaluationProvider,
    ) -> None:
        """
        Add a provider under its descriptor name.

        Raises:
            ProviderAlreadyRegisteredError: If the normalized provider name is
                already present.
        """
        descriptor = provider.descriptor
        provider_name = normalize_provider_name(descriptor.name)

        if provider_name in self._providers:
            raise ProviderAlreadyRegisteredError(
                f"Provider '{provider_name}' is already registered."
            )

        self._providers[provider_name] = provider

    def get(
        self,
        provider_name: str,
    ) -> EvaluationProvider:
        """
        Return a provider by name.

        Args:
            provider_name: Raw or normalized provider name.

        Raises:
            ProviderNotFoundError: If no provider is registered for the name.
        """
        normalized_name = normalize_provider_name(provider_name)

        try:
            return self._providers[normalized_name]
        except KeyError as exc:
            raise ProviderNotFoundError(
                f"Provider '{normalized_name}' is not registered."
            ) from exc

    def list(self) -> list[ProviderDescriptor]:
        """
        Return descriptors for all registered providers.
        """
        return [
            provider.descriptor
            for provider in self._providers.values()
        ]

    def contains(
        self,
        provider_name: str,
    ) -> bool:
        """
        Return whether a provider name is registered.
        """
        return normalize_provider_name(provider_name) in self._providers

    def unregister(
        self,
        provider_name: str,
    ) -> None:
        """
        Remove a provider from the registry.

        Raises:
            ProviderNotFoundError: If no provider is registered for the name.
        """
        normalized_name = normalize_provider_name(provider_name)

        if normalized_name not in self._providers:
            raise ProviderNotFoundError(
                f"Provider '{normalized_name}' is not registered."
            )

        del self._providers[normalized_name]
