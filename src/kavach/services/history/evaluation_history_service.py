from __future__ import annotations

from datetime import UTC, datetime

from kavach.domain.evaluation_result import EvaluationResult
from kavach.domain.history import (
    EvaluationComparison,
    EvaluationHistory,
    EvaluationHistoryMetric,
    EvaluationHistoryRecord,
    EvaluationMetricComparison,
    EvaluationSummary,
    EvaluationMetricTrend,
)
from kavach.governance import DriftAnalyzer, EvaluationDrift
from kavach.repositories.evaluation_repository import EvaluationRepository
from kavach.settings_control.operational import duration_seconds, setting_context
from kavach.tenancy.domain import TenantContext


class EvaluationHistoryRecordNotFoundError(Exception):
    """
    Raised when an evaluation is not present in an execution's history.
    """

    def __init__(
        self,
        execution_id: str,
        evaluation_id: str,
    ) -> None:
        self.execution_id = execution_id
        self.evaluation_id = evaluation_id
        super().__init__(
            f"Evaluation '{evaluation_id}' was not found in execution "
            f"'{execution_id}' history."
        )


class EvaluationHistoryService:
    """
    Application service for evaluation history and governance questions.

    Repositories store and retrieve evaluation results. This service turns
    those raw results into domain concepts such as history, summaries,
    comparisons, replay views, and drift analysis.
    """

    def __init__(
        self,
        evaluation_repository: EvaluationRepository,
        configuration_service=None,
    ) -> None:
        """
        Create the service with a repository implementation.
        """

        self._evaluation_repository = evaluation_repository
        self._configuration_service = configuration_service

    def get_execution_history(
        self,
        execution_id: str,
        context: TenantContext | None = None,
    ) -> EvaluationHistory:
        """
        Return every evaluation recorded for one workflow execution.
        """

        results = self._retained_results(execution_id, context)

        return EvaluationHistory(
            execution_id=execution_id,
            records=[self._to_history_record(result) for result in results],
        )

    def get_latest_evaluation(
        self,
        execution_id: str,
        context: TenantContext | None = None,
    ) -> EvaluationHistoryRecord | None:
        """
        Return the latest evaluation record for an execution.

        None means the execution has no persisted evaluations.
        """

        history = self.get_execution_history(execution_id, context)

        if not history.records:
            return None

        return history.records[-1]

    def get_metric_history(
        self,
        execution_id: str,
        metric_name: str,
        context: TenantContext | None = None,
    ) -> EvaluationMetricTrend:
        """
        Return a metric-specific trend for one execution.
        """

        history = self.get_execution_history(execution_id, context)

        return history.metric_trend(metric_name)

    def get_execution_summary(
        self,
        execution_id: str,
        context: TenantContext | None = None,
    ) -> EvaluationSummary:
        """
        Return a compact governance summary for one execution.
        """

        history = self.get_execution_history(execution_id, context)

        if not history.records:
            return EvaluationSummary(
                execution_id=execution_id,
                latest_score=None,
                evaluation_count=0,
                provider=None,
                provider_version=None,
                evaluated_at=None,
            )

        latest = history.records[-1]

        return EvaluationSummary(
            execution_id=execution_id,
            latest_score=self._average_metric_value(latest),
            evaluation_count=history.evaluation_count,
            provider=latest.evaluator_type,
            provider_version=latest.evaluator_version,
            evaluated_at=self._evaluated_at(latest.metadata),
        )

    def compare_evaluations(
        self,
        execution_id: str,
        baseline_evaluation_id: str,
        candidate_evaluation_id: str,
        context: TenantContext | None = None,
    ) -> EvaluationComparison:
        """
        Compare two evaluations from the same execution by metric name.

        Both evaluations must be present in the retained, tenant-scoped
        execution history.
        """

        history = self.get_execution_history(execution_id, context)
        baseline = self._find_record(
            history,
            baseline_evaluation_id,
        )
        candidate = self._find_record(
            history,
            candidate_evaluation_id,
        )

        baseline_metrics = self._metric_values_by_name(baseline)
        candidate_metrics = self._metric_values_by_name(candidate)

        return EvaluationComparison(
            execution_id=execution_id,
            baseline_evaluation_id=baseline_evaluation_id,
            candidate_evaluation_id=candidate_evaluation_id,
            metric_comparisons=[
                EvaluationMetricComparison(
                    metric_name=metric_name,
                    baseline_value=baseline_metrics.get(metric_name),
                    candidate_value=candidate_metrics.get(metric_name),
                )
                for metric_name in sorted(
                    baseline_metrics.keys() | candidate_metrics.keys()
                )
            ],
        )

    def analyze_drift(
        self,
        execution_id: str,
        baseline_evaluation_id: str,
        candidate_evaluation_id: str,
        context: TenantContext | None = None,
    ) -> EvaluationDrift:
        """
        Analyze governance drift between two evaluations.
        """

        results = self._retained_results(execution_id, context)
        baseline = self._find_result(
            results,
            execution_id,
            baseline_evaluation_id,
        )
        candidate = self._find_result(
            results,
            execution_id,
            candidate_evaluation_id,
        )

        return DriftAnalyzer().analyze(
            baseline=baseline,
            candidate=candidate,
        )

    def _retained_results(
        self,
        execution_id: str,
        context: TenantContext | None,
    ) -> list[EvaluationResult]:
        results = [
            result
            for result in self._evaluation_repository.find_by_execution_id(execution_id)
            if self._in_context(result, context)
        ]
        if self._configuration_service is not None:
            retention = duration_seconds(
                self._configuration_service.get(
                    "evaluation.retention", setting_context(context)
                )
            )
            cutoff = datetime.now(UTC).timestamp() - retention
            results = [
                result for result in results if result.created_at.timestamp() >= cutoff
            ]

        return sorted(
            results,
            key=lambda result: (result.created_at, result.evaluation_id),
        )

    @staticmethod
    def _to_history_record(
        result: EvaluationResult,
    ) -> EvaluationHistoryRecord:
        """
        Convert an EvaluationResult into the history read model.
        """

        return EvaluationHistoryRecord(
            evaluation_id=result.evaluation_id,
            execution_id=result.execution_id,
            evaluator_type=result.evaluator_type,
            evaluator_version=result.evaluator_version,
            metrics=[
                EvaluationHistoryMetric(
                    metric_name=metric.metric_name,
                    metric_value=metric.metric_value,
                    explanation=metric.explanation,
                )
                for metric in result.metrics
            ],
            metadata=result.metadata,
        )

    @staticmethod
    def _average_metric_value(
        record: EvaluationHistoryRecord,
    ) -> float | None:
        """
        Return the average score across metrics in an evaluation record.
        """

        if not record.metrics:
            return None

        return sum(metric.metric_value for metric in record.metrics) / len(
            record.metrics
        )

    @staticmethod
    def _evaluated_at(
        metadata: dict[str, object],
    ) -> str | None:
        """
        Extract evaluated_at from metadata when providers include it.
        """

        evaluated_at = metadata.get("evaluated_at")

        if evaluated_at is None:
            return None

        return str(evaluated_at)

    @staticmethod
    def _find_record(
        history: EvaluationHistory,
        evaluation_id: str,
    ) -> EvaluationHistoryRecord:
        """
        Find a history record by evaluation ID.
        """

        for record in history.records:
            if record.evaluation_id == evaluation_id:
                return record

        raise EvaluationHistoryRecordNotFoundError(
            execution_id=history.execution_id,
            evaluation_id=evaluation_id,
        )

    @staticmethod
    def _metric_values_by_name(
        record: EvaluationHistoryRecord,
    ) -> dict[str, float]:
        """
        Build a metric lookup for a history record.
        """

        return {metric.metric_name: metric.metric_value for metric in record.metrics}

    @staticmethod
    def _find_result(
        results: list[EvaluationResult],
        execution_id: str,
        evaluation_id: str,
    ) -> EvaluationResult:
        """
        Find an EvaluationResult by ID for drift analysis.
        """

        for result in results:
            if result.evaluation_id == evaluation_id:
                return result

        raise EvaluationHistoryRecordNotFoundError(
            execution_id=execution_id,
            evaluation_id=evaluation_id,
        )

    @staticmethod
    def _in_context(
        result: EvaluationResult,
        context: TenantContext | None,
    ) -> bool:
        return context is None or (
            result.organization_id == context.organization_id
            and result.project_id == (context.project_id or "")
        )
