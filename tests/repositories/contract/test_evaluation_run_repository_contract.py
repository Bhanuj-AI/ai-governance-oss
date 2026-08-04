from abc import ABC, abstractmethod
from datetime import UTC, datetime

from kavach.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
)
from kavach.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)


class EvaluationRunRepositoryContract(ABC):
    """
    Behavioral contract every EvaluationRunRepository implementation must satisfy.
    """

    @abstractmethod
    def repository(self) -> EvaluationRunRepository:
        """
        Return a fresh evaluation run repository instance.
        """

    def create_run(self) -> EvaluationRun:
        return EvaluationRun(
            run_id="run-1",
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            dataset_version="2026-06-26",
            evaluation_provider="TruLens",
            evaluation_result_id="evaluation-1",
            started_at=datetime(2026, 6, 26, tzinfo=UTC),
            completed_at=datetime(2026, 6, 26, 0, 1, tzinfo=UTC),
            status=EvaluationRunStatus.COMPLETED,
        )

    def test_should_save_and_load_evaluation_run(self) -> None:
        repository = self.repository()
        expected = self.create_run()

        repository.save(expected)

        assert repository.find_by_id(expected.run_id) == expected

    def test_should_find_runs_by_experiment_id(self) -> None:
        repository = self.repository()
        expected = self.create_run()

        repository.save(expected)

        assert repository.find_by_experiment_id(expected.experiment_id) == [
            expected
        ]
        assert repository.find_by_experiment_id("missing") == []

    def test_should_find_runs_by_candidate_id(self) -> None:
        repository = self.repository()
        expected = self.create_run()

        repository.save(expected)

        assert repository.find_by_candidate_id(expected.candidate_id) == [
            expected
        ]
        assert repository.find_by_candidate_id("missing") == []

    def test_should_replace_run_with_same_id(self) -> None:
        repository = self.repository()
        expected = self.create_run()
        replacement = EvaluationRun(
            run_id=expected.run_id,
            experiment_id=expected.experiment_id,
            candidate_id=expected.candidate_id,
            dataset_version=expected.dataset_version,
            evaluation_provider=expected.evaluation_provider,
            evaluation_result_id=expected.evaluation_result_id,
            started_at=expected.started_at,
            completed_at=expected.completed_at,
            status=EvaluationRunStatus.FAILED,
        )

        repository.save(expected)
        repository.save(replacement)

        assert repository.find_by_id(expected.run_id) == replacement

    def test_should_find_all_runs(self) -> None:
        repository = self.repository()
        expected = self.create_run()

        repository.save(expected)

        assert repository.find_all() == [expected]
