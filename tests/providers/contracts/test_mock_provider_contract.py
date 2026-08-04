from __future__ import annotations

from kavach.providers.mock_provider import MockEvaluationProvider
from kavach.providers.evaluation_provider import EvaluationProvider
from tests.providers.contracts.provider_contract import ProviderContract


class TestMockProviderContract(ProviderContract):
    def provider(self) -> EvaluationProvider:
        return MockEvaluationProvider()
