from __future__ import annotations

from typing import Any

from ai_governance.providers.evaluation_provider import EvaluationProvider
from ai_governance.providers.trulens import TruLensAdapter
from tests.providers.contracts.provider_contract import ProviderContract


class _FakeTruLensOpenAI:
    def relevance(
        self,
        prompt: str,
        response: str,
    ) -> float:
        return 0.91

    def context_relevance(
        self,
        question: str,
        context: str,
    ) -> float:
        return 0.88

    def groundedness_measure_with_cot_reasons(
        self,
        source: str,
        statement: str,
    ) -> tuple[float, dict[str, Any]]:
        return 0.86, {"reason": "grounded"}


class TestTruLensAdapterContract(ProviderContract):
    def provider(self) -> EvaluationProvider:
        return TruLensAdapter(
            llm_provider=_FakeTruLensOpenAI(),  # type: ignore[arg-type]
            judge_model="fake-judge",
        )
