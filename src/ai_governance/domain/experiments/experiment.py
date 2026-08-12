from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ExperimentStatus(str, Enum):
    """
    Lifecycle state for an experiment orchestration aggregate.
    """

    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class Experiment:
    """
    Immutable experiment metadata governed by the experiment service.

    Experiments are the orchestration aggregate for experiment management. They
    intentionally remain small and reference governed assets through adjacent
    capabilities rather than embedding prompt, model, or dataset data directly.
    """

    experiment_id: str
    name: str
    description: str
    owner: str
    created_at: datetime
    status: ExperimentStatus
    organization_id: str = "org_default"
    project_id: str = "project_default"
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self._require_non_empty("experiment_id", self.experiment_id)
        self._require_non_empty("name", self.name)
        self._require_non_empty("description", self.description)
        self._require_non_empty("owner", self.owner)
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", self.created_at)

    @staticmethod
    def _require_non_empty(
        field_name: str,
        value: str,
    ) -> None:
        if not value.strip():
            raise ValueError(f"Experiment {field_name} must not be empty.")
