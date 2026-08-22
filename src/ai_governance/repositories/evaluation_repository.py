from abc import ABC, abstractmethod
from dataclasses import dataclass

from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.tenancy.domain import TenantContext


@dataclass(frozen=True)
class EvaluationResultPage:
    """Tenant-scoped page of item-level evaluation results."""

    items: tuple[EvaluationResult, ...]
    total_count: int


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

    @abstractmethod
    def find_page_by_execution_id_prefix(
        self,
        execution_id_prefix: str,
        context: TenantContext,
        *,
        offset: int,
        limit: int,
    ) -> EvaluationResultPage:
        """Return ordered evaluation results belonging to one execution family."""
