from __future__ import annotations

from kavach.domain.evaluation_result import EvaluationResult
from kavach.repositories.evaluation_repository import (
    EvaluationRepository,
)


class InMemoryEvaluationRepository(EvaluationRepository):
    def __init__(self) -> None:
        self._results: list[EvaluationResult] = []

    def save(
        self,
        result: EvaluationResult,
    ) -> None:
        self._results.append(result)

    def find_by_evaluation_id(
        self,
        evaluation_id: str,
    ) -> EvaluationResult | None:
        return next(
            (
                result
                for result in self._results
                if result.evaluation_id == evaluation_id
            ),
            None,
        )

    def find_by_execution_id(
        self,
        execution_id: str,
    ) -> list[EvaluationResult]:

        return [
            result for result in self._results if result.execution_id == execution_id
        ]
