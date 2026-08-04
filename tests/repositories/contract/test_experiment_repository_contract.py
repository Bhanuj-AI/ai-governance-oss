from abc import ABC, abstractmethod
from datetime import UTC, datetime

from kavach.domain.experiments import (
    Experiment,
    ExperimentStatus,
)
from kavach.repositories.experiment_repository import ExperimentRepository


class ExperimentRepositoryContract(ABC):
    """
    Behavioral contract every ExperimentRepository implementation must satisfy.
    """

    @abstractmethod
    def repository(self) -> ExperimentRepository:
        """
        Return a fresh experiment repository instance.
        """

    def create_experiment(self) -> Experiment:
        return Experiment(
            experiment_id="experiment-1",
            name="support-prompt-benchmark",
            description="Compare support prompt revisions.",
            owner="governance-team",
            created_at=datetime(2026, 6, 26, tzinfo=UTC),
            status=ExperimentStatus.DRAFT,
        )

    def test_should_save_and_load_experiment(self) -> None:
        repository = self.repository()
        expected = self.create_experiment()

        repository.save(expected)

        assert repository.find_by_id(expected.experiment_id) == expected

    def test_should_find_experiment_by_name(self) -> None:
        repository = self.repository()
        expected = self.create_experiment()

        repository.save(expected)

        assert repository.find_by_name(expected.name) == expected
        assert repository.find_by_name("missing") is None

    def test_should_replace_experiment_with_same_id(self) -> None:
        repository = self.repository()
        expected = self.create_experiment()
        replacement = Experiment(
            experiment_id=expected.experiment_id,
            name=expected.name,
            description=expected.description,
            owner=expected.owner,
            created_at=expected.created_at,
            status=ExperimentStatus.RUNNING,
        )

        repository.save(expected)
        repository.save(replacement)

        assert repository.find_by_id(expected.experiment_id) == replacement

    def test_should_find_all_experiments(self) -> None:
        repository = self.repository()
        expected = self.create_experiment()

        repository.save(expected)

        assert repository.find_all() == [expected]
