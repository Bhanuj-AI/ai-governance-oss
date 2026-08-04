from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from kavach.domain.assets import AssetProvenance


class ModelStatus(str, Enum):
    """
    Governance lifecycle state for a registered model version.
    """

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class Model:
    """
    Immutable, versioned AI model artifact used by experiments.

    A model registry record represents the exact model version and governance
    metadata that an experiment candidate, evaluation, or deployment decision
    should reference for reproducibility.
    """

    model_id: str
    provider: str
    model_name: str
    version: str
    parameters: dict[str, Any]
    cost: dict[str, float] | None
    latency: float | None
    context_window: int
    creator: str
    created_at: datetime
    status: ModelStatus
    provenance: AssetProvenance = AssetProvenance.MANAGED
    source_system: str | None = None
    source_reference: str | None = None
    tenant_id: str = "org_default"
    organization_id: str = "org_default"
    project_id: str = "project_default"

    def __post_init__(self) -> None:
        self._require_non_empty("model_id", self.model_id)
        self._require_non_empty("provider", self.provider)
        self._require_non_empty("model_name", self.model_name)
        self._require_non_empty("version", self.version)
        self._require_non_empty("creator", self.creator)
        self._require_non_empty("tenant_id", self.tenant_id)
        self._require_non_empty("organization_id", self.organization_id)
        self._require_non_empty("project_id", self.project_id)

        if self.context_window <= 0:
            raise ValueError("Model context_window must be greater than zero.")

        if self.latency is not None and self.latency < 0:
            raise ValueError("Model latency must not be negative.")

        if self.cost is not None:
            for key, value in self.cost.items():
                self._require_non_empty("cost key", key)

                if value < 0:
                    raise ValueError("Model cost values must not be negative.")

        object.__setattr__(self, "parameters", dict(self.parameters))

        if self.cost is not None:
            object.__setattr__(self, "cost", dict(self.cost))

        if self.provenance != AssetProvenance.MANAGED:
            self._require_non_empty("source_system", self.source_system or "")

    @staticmethod
    def _require_non_empty(
        field_name: str,
        value: str,
    ) -> None:
        if not value.strip():
            raise ValueError(f"Model {field_name} must not be empty.")


@dataclass(frozen=True)
class ModelParameterChange:
    """
    Parameter-level difference between two model versions.
    """

    parameter_name: str
    baseline_value: Any
    candidate_value: Any


@dataclass(frozen=True)
class ModelDiff:
    """
    Governance diff between two model versions.

    This captures model metadata changes before evaluation results are compared,
    making experiment reviews explicit about what changed in the candidate.
    """

    baseline_model_id: str
    candidate_model_id: str
    provider_changed: bool
    version_changed: bool
    context_window_changed: bool
    cost_changed: bool
    latency_changed: bool
    parameters_added: tuple[str, ...]
    parameters_removed: tuple[str, ...]
    parameters_changed: tuple[ModelParameterChange, ...]

    @property
    def has_changes(self) -> bool:
        """
        Return whether any governed model metadata changed.
        """

        return any(
            [
                self.provider_changed,
                self.version_changed,
                self.context_window_changed,
                self.cost_changed,
                self.latency_changed,
                bool(self.parameters_added),
                bool(self.parameters_removed),
                bool(self.parameters_changed),
            ]
        )
