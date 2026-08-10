from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ai_governance.evaluation.evaluation_metrics import normalize_metric_name


@dataclass(frozen=True)
class ProviderCapabilities:
    """
    Describes the behavior an evaluation provider exposes through AI Governance Control Plane.

    Capabilities are contract-level promises made by an adapter, not a full
    list of everything the underlying vendor or framework may support. Callers
    can use them to discover metrics, choose compatible providers, and avoid
    invoking workflows the adapter cannot safely handle.

    Example:
        capabilities = ProviderCapabilities(
            supported_metrics=("answer_relevance", "groundedness"),
            supported_evaluation_modes=("sync",),
            supports_artifacts=True,
            supports_explanations=True,
        )

        if "groundedness" in capabilities.supported_metrics:
            ...
    """

    supported_metrics: tuple[str, ...]
    supported_evaluation_modes: tuple[str, ...] = ("sync",)
    supports_batch: bool = False
    supports_async: bool = False
    supports_artifacts: bool = True
    supports_explanations: bool = True
    supports_row_level_results: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Normalize metrics and defensive-copy mutable input values.
        """
        object.__setattr__(
            self,
            "supported_metrics",
            tuple(
                normalize_metric_name(metric)
                for metric in self.supported_metrics
            ),
        )
        object.__setattr__(
            self,
            "supported_evaluation_modes",
            tuple(self.supported_evaluation_modes),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """
        Return a JSON-serializable representation for APIs and snapshots.
        """
        return {
            "supported_metrics": list(self.supported_metrics),
            "supported_evaluation_modes": list(
                self.supported_evaluation_modes
            ),
            "supports_batch": self.supports_batch,
            "supports_async": self.supports_async,
            "supports_artifacts": self.supports_artifacts,
            "supports_explanations": self.supports_explanations,
            "supports_row_level_results": self.supports_row_level_results,
            "metadata": dict(self.metadata),
        }
