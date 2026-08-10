from __future__ import annotations

from abc import ABC, abstractmethod

from ai_governance.domain.experiments import ExperimentCandidate


class ExperimentCandidateRepository(ABC):
    """
    Persistence contract for experiment candidates.

    Repositories store immutable candidate records. Validation, lifecycle
    constraints, and reference integrity are owned by
    ExperimentCandidateService.
    """

    @abstractmethod
    def save(
        self,
        candidate: ExperimentCandidate,
    ) -> None:
        pass

    @abstractmethod
    def find_by_id(
        self,
        candidate_id: str,
    ) -> ExperimentCandidate | None:
        pass

    @abstractmethod
    def find_by_experiment_id(
        self,
        experiment_id: str,
    ) -> list[ExperimentCandidate]:
        pass

    @abstractmethod
    def find_all(self) -> list[ExperimentCandidate]:
        pass
