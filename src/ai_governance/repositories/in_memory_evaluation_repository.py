from __future__ import annotations

from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.repositories.evaluation_repository import (
    EvaluationRepository,
    EvaluationResultPage,
)
from ai_governance.tenancy.domain import TenantContext


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

    def find_page_by_execution_id_prefix(
        self,
        execution_id_prefix: str,
        context: TenantContext,
        *,
        offset: int,
        limit: int,
    ) -> EvaluationResultPage:
        results = sorted(
            (
                result
                for result in self._results
                if result.execution_id.startswith(execution_id_prefix)
                and result.organization_id == context.organization_id
                and result.project_id == (context.project_id or "")
            ),
            key=lambda result: (
                result.created_at,
                result.execution_id,
                result.evaluation_id,
            ),
        )
        return EvaluationResultPage(
            items=tuple(results[offset : offset + limit]),
            total_count=len(results),
        )
