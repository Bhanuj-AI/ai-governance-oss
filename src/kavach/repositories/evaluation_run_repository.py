from __future__ import annotations

from abc import ABC, abstractmethod

from kavach.domain.experiments import EvaluationRun


class EvaluationRunRepository(ABC):
    """
    Persistence contract for experiment evaluation runs.
    """

    @abstractmethod
    def save(
        self,
        run: EvaluationRun,
    ) -> None:
        pass

    @abstractmethod
    def find_by_id(
        self,
        run_id: str,
    ) -> EvaluationRun | None:
        pass

    @abstractmethod
    def find_by_experiment_id(
        self,
        experiment_id: str,
    ) -> list[EvaluationRun]:
        pass

    @abstractmethod
    def find_by_candidate_id(
        self,
        candidate_id: str,
    ) -> list[EvaluationRun]:
        pass

    @abstractmethod
    def find_all(self) -> list[EvaluationRun]:
        pass
