import pytest

from ai_governance.providers import (
    LLMProviderRegistry,
    ProviderAlreadyRegisteredError,
    ProviderCapabilities,
    ProviderDescriptor,
)
from ai_governance.spi import LLMCompletion


class FakeLLMProvider:
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="fake-llm",
            display_name="Fake LLM",
            version="1",
            adapter_version="1",
            capabilities=ProviderCapabilities(supported_metrics=()),
        )

    def complete(self, *, model: str, system_prompt: str, user_prompt: str) -> LLMCompletion:
        return LLMCompletion(text="{}", model=model)


def test_llm_provider_registry_is_provider_neutral() -> None:
    provider = FakeLLMProvider()
    registry = LLMProviderRegistry((provider,))

    assert registry.get("FAKE_LLM") is provider
    assert registry.list()[0].name == "fake_llm"
    with pytest.raises(ProviderAlreadyRegisteredError):
        registry.register(provider)
