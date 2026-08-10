from abc import ABC
from abc import abstractmethod

from ai_governance.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.repositories.evaluation_repository import EvaluationRepository


class EvaluationRepositoryContract(ABC):
    """
    Behavioral contract that every EvaluationRepository implementation
    must satisfy.
    """

    @abstractmethod
    def repository(self) -> EvaluationRepository:
        """
        Return a fresh repository instance.
        """

    def create_evaluation_result(self) -> EvaluationResult:
        return EvaluationResult(
            evaluation_id="evaluation-1",
            execution_id="execution-1",
            evaluator_type="trulens",
            evaluator_version="1.0.0",
            metrics=[
                EvaluationMetric(
                    metric_name="ANSWER_RELEVANCE",
                    metric_value=0.94,
                    explanation="Relevant",
                ),
                EvaluationMetric(
                    metric_name="GROUNDEDNESS",
                    metric_value=0.88,
                    explanation="Grounded",
                ),
            ],
            metadata={
                "model": "gpt-4o-mini",
            },
        )

    def test_should_save_and_load_evaluation_result(self) -> None:

        repository = self.repository()

        expected = self.create_evaluation_result()

        repository.save(expected)

        actual = repository.find_by_execution_id(expected.execution_id)

        assert actual == [expected]
        assert (
            repository.find_by_evaluation_id(expected.evaluation_id)
            == expected
        )

    def test_should_return_empty_list_when_execution_does_not_exist(
        self,
    ) -> None:

        repository = self.repository()

        assert repository.find_by_execution_id("missing") == []
        assert repository.find_by_evaluation_id("missing") is None

    def test_should_replace_existing_evaluation(self) -> None:

        repository = self.repository()

        expected = self.create_evaluation_result()

        repository.save(expected)
        repository.save(expected)

        actual = repository.find_by_execution_id(expected.execution_id)

        assert actual == [expected]

    def test_should_return_all_evaluations_for_execution(self) -> None:

        repository = self.repository()

        first = self.create_evaluation_result()
        second = EvaluationResult(
            evaluation_id="evaluation-2",
            execution_id=first.execution_id,
            evaluator_type="trulens",
            evaluator_version="1.0.0",
            metrics=[
                EvaluationMetric(
                    metric_name="ANSWER_RELEVANCE",
                    metric_value=0.91,
                    explanation="Mostly relevant",
                ),
            ],
            metadata={
                "model": "gpt-4o-mini",
            },
        )

        repository.save(first)
        repository.save(second)

        actual = repository.find_by_execution_id(first.execution_id)

        assert actual == [
            first,
            second,
        ]
