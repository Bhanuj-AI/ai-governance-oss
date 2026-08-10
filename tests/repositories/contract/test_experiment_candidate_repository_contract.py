from abc import ABC, abstractmethod
from datetime import UTC, datetime

from ai_governance.domain.experiments import ExperimentCandidate
from ai_governance.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)


class ExperimentCandidateRepositoryContract(ABC):
    """
    Behavioral contract every ExperimentCandidateRepository implementation
    must satisfy.
    """

    @abstractmethod
    def repository(self) -> ExperimentCandidateRepository:
        """
        Return a fresh candidate repository instance.
        """

    def create_candidate(self) -> ExperimentCandidate:
        return ExperimentCandidate(
            candidate_id="candidate-1",
            experiment_id="experiment-1",
            name="Baseline",
            prompt_id="prompt-1",
            prompt_version="v1",
            model_id="model-1",
            model_version="2026-06-25",
            dataset_id="dataset-1",
            dataset_version="2026-06-26",
            evaluation_provider="TruLens",
            temperature=0.0,
            top_p=1.0,
            max_tokens=4096,
            metadata={"tier": "baseline"},
            created_at=datetime(2026, 6, 26, tzinfo=UTC),
        )

    def test_should_save_and_load_candidate(self) -> None:
        repository = self.repository()
        expected = self.create_candidate()

        repository.save(expected)

        assert repository.find_by_id(expected.candidate_id) == expected

    def test_should_find_candidates_for_experiment(self) -> None:
        repository = self.repository()
        expected = self.create_candidate()

        repository.save(expected)

        assert repository.find_by_experiment_id(expected.experiment_id) == [
            expected
        ]
        assert repository.find_by_experiment_id("missing") == []

    def test_should_replace_candidate_with_same_id(self) -> None:
        repository = self.repository()
        expected = self.create_candidate()
        replacement = ExperimentCandidate(
            candidate_id=expected.candidate_id,
            experiment_id=expected.experiment_id,
            name=expected.name,
            prompt_id=expected.prompt_id,
            prompt_version=expected.prompt_version,
            model_id=expected.model_id,
            model_version=expected.model_version,
            dataset_id=expected.dataset_id,
            dataset_version=expected.dataset_version,
            evaluation_provider="Phoenix",
            temperature=0.2,
            top_p=0.95,
            max_tokens=8192,
            metadata={"tier": "replacement"},
            created_at=expected.created_at,
        )

        repository.save(expected)
        repository.save(replacement)

        assert repository.find_by_id(expected.candidate_id) == replacement

    def test_should_find_all_candidates(self) -> None:
        repository = self.repository()
        expected = self.create_candidate()

        repository.save(expected)

        assert repository.find_all() == [expected]
