from __future__ import annotations

from kavach.domain.experiments import ExperimentCandidate
from kavach.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)


class InMemoryExperimentCandidateRepository(
    ExperimentCandidateRepository
):
    """
    In-memory ExperimentCandidateRepository used by tests and local workflows.
    """

    def __init__(self) -> None:
        self._candidates_by_id: dict[str, ExperimentCandidate] = {}

    def save(
        self,
        candidate: ExperimentCandidate,
    ) -> None:
        self._candidates_by_id[candidate.candidate_id] = candidate

    def find_by_id(
        self,
        candidate_id: str,
    ) -> ExperimentCandidate | None:
        return self._candidates_by_id.get(candidate_id)

    def find_by_experiment_id(
        self,
        experiment_id: str,
    ) -> list[ExperimentCandidate]:
        return [
            candidate
            for candidate in self._candidates_by_id.values()
            if candidate.experiment_id == experiment_id
        ]

    def find_all(self) -> list[ExperimentCandidate]:
        return list(self._candidates_by_id.values())
