"""
Provider registry wiring for the Kavach platform.
"""

from __future__ import annotations

import os
from typing import Any


def get_provider_registry() -> Any:
    """
    Create the provider registry used by REST request dependencies.
    """

    from kavach.providers import EvaluationProviderRegistry
    from kavach.providers.mock_provider import MockEvaluationProvider

    registry = EvaluationProviderRegistry()
    registry.register(MockEvaluationProvider())
    if _trulens_is_configured():
        from kavach.providers.trulens import TruLensAdapter

        registry.register(TruLensAdapter())
    return registry


def _trulens_is_configured() -> bool:
    """Only expose TruLens when the runtime can execute it safely."""

    return bool(
        os.getenv("OPENAI_API_KEY", "").strip()
        and (
            os.getenv("KAVACH_TRULENS_MODEL", "").strip()
            or os.getenv("OPENAI_DEFAULT_JUDGE_MODEL", "").strip()
        )
    )
