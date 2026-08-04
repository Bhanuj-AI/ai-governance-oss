from __future__ import annotations

from kavach.domain.evaluation_result import EvaluationResult
from kavach.domain.history import EvaluationComparison
from kavach.governance import EvaluationDrift
from kavach.repositories.evaluation_repository import EvaluationRepository
from kavach.services.evaluation_api_service import EvaluationNotFoundError
from kavach.services.history import EvaluationHistoryService


class GovernanceReportNotImplementedError(Exception):
    """
    Raised when no governance report generator is configured.
    """

    def __init__(
        self,
        evaluation_id: str,
    ) -> None:
        self.evaluation_id = evaluation_id
        super().__init__(
            "Governance report retrieval is not implemented for this runtime."
        )


class InvalidGovernanceRequestError(Exception):
    """
    Raised when governance inputs are internally inconsistent.
    """


class GovernanceApiService:
    """
    Application facade for REST governance use cases.
    """

    def __init__(
        self,
        evaluation_repository: EvaluationRepository,
    ) -> None:
        self._evaluation_repository = evaluation_repository
        self._history_service = EvaluationHistoryService(
            evaluation_repository
        )

    def compare_evaluations(
        self,
        baseline_evaluation_id: str,
        candidate_evaluation_id: str,
    ) -> EvaluationComparison:
        """
        Compare two persisted evaluations using the history service.
        """
        baseline, candidate = self._paired_evaluations(
            baseline_evaluation_id=baseline_evaluation_id,
            candidate_evaluation_id=candidate_evaluation_id,
        )
        return self._history_service.compare_evaluations(
            execution_id=baseline.execution_id,
            baseline_evaluation_id=baseline.evaluation_id,
            candidate_evaluation_id=candidate.evaluation_id,
        )

    def analyze_drift(
        self,
        baseline_evaluation_id: str,
        candidate_evaluation_id: str,
    ) -> EvaluationDrift:
        """
        Analyze drift between two persisted evaluations.
        """
        baseline, candidate = self._paired_evaluations(
            baseline_evaluation_id=baseline_evaluation_id,
            candidate_evaluation_id=candidate_evaluation_id,
        )
        return self._history_service.analyze_drift(
            execution_id=baseline.execution_id,
            baseline_evaluation_id=baseline.evaluation_id,
            candidate_evaluation_id=candidate.evaluation_id,
        )

    def get_report(
        self,
        evaluation_id: str,
    ) -> None:
        """
        Report generation is not yet backed by an existing service.
        """
        self._evaluation_by_id(evaluation_id)
        raise GovernanceReportNotImplementedError(evaluation_id)

    def _paired_evaluations(
        self,
        baseline_evaluation_id: str,
        candidate_evaluation_id: str,
    ) -> tuple[EvaluationResult, EvaluationResult]:
        baseline = self._evaluation_by_id(baseline_evaluation_id)
        candidate = self._evaluation_by_id(candidate_evaluation_id)
        if baseline.execution_id != candidate.execution_id:
            raise InvalidGovernanceRequestError(
                "Evaluations must belong to the same execution."
            )

        return baseline, candidate

    def _evaluation_by_id(
        self,
        evaluation_id: str,
    ) -> EvaluationResult:
        result = self._evaluation_repository.find_by_evaluation_id(
            evaluation_id
        )
        if result is None:
            raise EvaluationNotFoundError(evaluation_id=evaluation_id)
        return result
