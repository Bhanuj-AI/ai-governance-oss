from abc import ABC
from abc import abstractmethod

from kavach.domain.evaluation_result import EvaluationResult


class EvaluationRepository(ABC):
    @abstractmethod
    def save(self, result: EvaluationResult) -> None:
        pass

    @abstractmethod
    def find_by_evaluation_id(
        self,
        evaluation_id: str,
    ) -> EvaluationResult | None:
        pass

    @abstractmethod
    def find_by_execution_id(
        self,
        execution_id: str,
    ) -> list[EvaluationResult]:
        pass
