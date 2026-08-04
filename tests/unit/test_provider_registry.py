from __future__ import annotations

import pytest

from kavach.providers import (
    EvaluationProviderRegistry,
    MockEvaluationProvider,
    ProviderAlreadyRegisteredError,
    ProviderNotFoundError,
)


def test_provider_registry_registers_and_resolves_provider() -> None:
    registry = EvaluationProviderRegistry()
    provider = MockEvaluationProvider()

    registry.register(provider)

    assert registry.contains("Mock")
    assert registry.get("mock") is provider
    assert registry.list() == [provider.descriptor]


def test_provider_registry_rejects_duplicate_provider_names() -> None:
    registry = EvaluationProviderRegistry()

    registry.register(MockEvaluationProvider())

    with pytest.raises(ProviderAlreadyRegisteredError):
        registry.register(MockEvaluationProvider())


def test_provider_registry_rejects_missing_provider_lookup() -> None:
    registry = EvaluationProviderRegistry()

    with pytest.raises(ProviderNotFoundError):
        registry.get("missing")
