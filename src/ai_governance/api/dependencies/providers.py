"""
Provider registry wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

import os
from typing import Any


def get_provider_registry() -> Any:
    """
    Create the provider registry used by REST request dependencies.
    """

    from ai_governance.providers import EvaluationProviderRegistry
    from ai_governance.providers.mock_provider import MockEvaluationProvider

    registry = EvaluationProviderRegistry()
    registry.register(MockEvaluationProvider())
    if _trulens_is_configured():
        from ai_governance.providers.trulens import TruLensAdapter

        registry.register(TruLensAdapter())
    return registry


def _trulens_is_configured() -> bool:
    """Only expose TruLens when the runtime can execute it safely."""

    return bool(
        os.getenv("OPENAI_API_KEY", "").strip()
        and (
            os.getenv("AI_GOVERNANCE_TRULENS_MODEL", "").strip()
            or os.getenv("OPENAI_DEFAULT_JUDGE_MODEL", "").strip()
        )
    )
