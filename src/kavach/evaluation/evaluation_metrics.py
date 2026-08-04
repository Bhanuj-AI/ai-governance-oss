from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from collections.abc import Mapping

ANSWER_RELEVANCE = "answer_relevance"
CONTEXT_RELEVANCE = "context_relevance"
GROUNDEDNESS = "groundedness"

SUPPORTED_EVALUATION_METRICS = frozenset(
    {
        ANSWER_RELEVANCE,
        CONTEXT_RELEVANCE,
        GROUNDEDNESS,
    }
)

_METRIC_ALIASES = {
    ANSWER_RELEVANCE: ANSWER_RELEVANCE,
    CONTEXT_RELEVANCE: CONTEXT_RELEVANCE,
    GROUNDEDNESS: GROUNDEDNESS,
    "Answer Relevance": ANSWER_RELEVANCE,
    "Context Relevance": CONTEXT_RELEVANCE,
    "Groundedness": GROUNDEDNESS,
    "ANSWER_RELEVANCE": ANSWER_RELEVANCE,
    "CONTEXT_RELEVANCE": CONTEXT_RELEVANCE,
    "GROUNDEDNESS": GROUNDEDNESS,
}


def normalize_metric_name(
    name: str,
) -> str:
    """
    Normalize a human or provider-facing metric name into Kavach's key format.

    Example:
        normalize_metric_name("Answer Relevance") == "answer_relevance"
    """
    normalized = name.strip()

    if normalized in _METRIC_ALIASES:
        return _METRIC_ALIASES[normalized]

    return normalized.lower().replace(" ", "_")


@dataclass(frozen=True)
class EvaluationMetricSpec:
    """
    Requested metric definition for an evaluation provider.

    Metric specs let callers ask for canonical Kavach metrics while optionally
    adding provider-neutral hints such as a threshold, weight, description, or
    metadata. Providers may map the canonical name to their own metric
    implementation.

    Example:
        EvaluationMetricSpec(
            name="groundedness",
            threshold=0.8,
            weight=2.0,
            metadata={"rubric": "strict"},
        )
    """

    name: str
    description: str | None = None
    threshold: float | None = None
    weight: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Normalize the metric name and freeze metadata after construction.
        """
        object.__setattr__(self, "name", normalize_metric_name(self.name))
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )
