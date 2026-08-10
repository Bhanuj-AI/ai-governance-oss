"""Registry for governed LLM provider adapters."""

from __future__ import annotations

from collections.abc import Iterable

from ai_governance.providers.errors import ProviderAlreadyRegisteredError, ProviderNotFoundError
from ai_governance.providers.provider_descriptor import ProviderDescriptor, normalize_provider_name
from ai_governance.spi.llm import LLMProvider


class LLMProviderRegistry:
    """Resolve registered text-generation adapters by governed provider name."""

    def __init__(self, providers: Iterable[LLMProvider] = ()) -> None:
        self._providers: dict[str, LLMProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: LLMProvider) -> None:
        name = normalize_provider_name(provider.descriptor.name)
        if name in self._providers:
            raise ProviderAlreadyRegisteredError(f"Provider '{name}' is already registered.")
        self._providers[name] = provider

    def get(self, provider_name: str) -> LLMProvider:
        name = normalize_provider_name(provider_name)
        try:
            return self._providers[name]
        except KeyError as error:
            raise ProviderNotFoundError(f"Provider '{name}' is not registered.") from error

    def list(self) -> list[ProviderDescriptor]:
        return [provider.descriptor for provider in self._providers.values()]

    def contains(self, provider_name: str) -> bool:
        return normalize_provider_name(provider_name) in self._providers


__all__ = ["LLMProviderRegistry"]
