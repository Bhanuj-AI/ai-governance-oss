from __future__ import annotations

from kavach.domain.experiments import EvaluationRun
from kavach.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)


class InMemoryEvaluationRunRepository(EvaluationRunRepository):
    """
    In-memory EvaluationRunRepository used by tests and local workflows.
    """

    def __init__(self) -> None:
        self._runs_by_id: dict[str, EvaluationRun] = {}

    def save(
        self,
        run: EvaluationRun,
    ) -> None:
        self._runs_by_id[run.run_id] = run

    def find_by_id(
        self,
        run_id: str,
    ) -> EvaluationRun | None:
        return self._runs_by_id.get(run_id)

    def find_by_experiment_id(
        self,
        experiment_id: str,
    ) -> list[EvaluationRun]:
        return [
            run
            for run in self._runs_by_id.values()
            if run.experiment_id == experiment_id
        ]

    def find_by_candidate_id(
        self,
        candidate_id: str,
    ) -> list[EvaluationRun]:
        return [
            run
            for run in self._runs_by_id.values()
            if run.candidate_id == candidate_id
        ]

    def find_all(self) -> list[EvaluationRun]:
        return list(self._runs_by_id.values())
