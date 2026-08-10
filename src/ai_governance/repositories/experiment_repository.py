from __future__ import annotations

from abc import ABC, abstractmethod

from ai_governance.domain.experiments import Experiment


class ExperimentRepository(ABC):
    """
    Persistence contract for experiments.

    Repositories store experiment metadata. Lifecycle and orchestration rules
    are owned by ExperimentService.
    """

    @abstractmethod
    def save(
        self,
        experiment: Experiment,
    ) -> None:
        pass

    @abstractmethod
    def find_by_id(
        self,
        experiment_id: str,
    ) -> Experiment | None:
        pass

    @abstractmethod
    def find_by_name(
        self,
        name: str,
    ) -> Experiment | None:
        pass

    @abstractmethod
    def find_all(self) -> list[Experiment]:
        pass
