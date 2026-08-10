from __future__ import annotations

from ai_governance.domain.experiments import Experiment
from ai_governance.repositories.experiment_repository import ExperimentRepository


class InMemoryExperimentRepository(ExperimentRepository):
    """
    In-memory ExperimentRepository used by tests and local workflows.
    """

    def __init__(self) -> None:
        self._experiments_by_id: dict[str, Experiment] = {}

    def save(
        self,
        experiment: Experiment,
    ) -> None:
        self._experiments_by_id[experiment.experiment_id] = experiment

    def find_by_id(
        self,
        experiment_id: str,
    ) -> Experiment | None:
        return self._experiments_by_id.get(experiment_id)

    def find_by_name(
        self,
        name: str,
    ) -> Experiment | None:
        return next(
            (
                experiment
                for experiment in self._experiments_by_id.values()
                if experiment.name == name
            ),
            None,
        )

    def find_all(self) -> list[Experiment]:
        return list(self._experiments_by_id.values())
