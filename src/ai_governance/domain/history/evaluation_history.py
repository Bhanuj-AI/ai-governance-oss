from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvaluationHistoryMetric:
    """
    Metric value captured inside a historical evaluation record.

    This mirrors EvaluationMetric while keeping history read models separate
    from provider output models. The separation lets governance evolve without
    changing evaluation provider contracts.
    """

    metric_name: str
    metric_value: float
    explanation: str | None = None


@dataclass(frozen=True)
class EvaluationHistoryRecord:
    """
    Governance read model for one persisted evaluation result.

    History records are what services and APIs return instead of raw repository
    rows. They preserve provider identity, metric values, and metadata needed
    by summaries, comparisons, drift analysis, and replay views.
    """

    evaluation_id: str
    execution_id: str
    evaluator_type: str
    evaluator_version: str
    metrics: list[EvaluationHistoryMetric]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class EvaluationMetricTrendPoint:
    """
    Single point in a metric trend for one evaluation.

    Trend points intentionally carry provider identity so future reports can
    explain whether a score shift came from model behavior or evaluator changes.
    """

    evaluation_id: str
    execution_id: str
    evaluator_type: str
    evaluator_version: str
    metric_value: float
    explanation: str | None = None


@dataclass(frozen=True)
class EvaluationMetricTrend:
    """
    Time-ordered read model for one metric across evaluations.

    The current repository preserves insertion order for in-memory data and
    stable evaluation ordering for SQLite. This model keeps the trend concept
    independent from any particular storage engine.
    """

    metric_name: str
    points: list[EvaluationMetricTrendPoint]

    @property
    def evaluation_count(self) -> int:
        """
        Return the number of evaluations that include this metric.
        """

        return len(self.points)

    @property
    def average_metric_value(self) -> float | None:
        """
        Return the average metric value across trend points.

        None means the metric was never observed for the requested history.
        """

        if not self.points:
            return None

        return sum(point.metric_value for point in self.points) / len(
            self.points
        )


@dataclass(frozen=True)
class EvaluationHistory:
    """
    All evaluation records associated with one workflow execution.

    This is the central history read model used by governance APIs, replay
    integration, summaries, comparisons, and drift analysis.
    """

    execution_id: str
    records: list[EvaluationHistoryRecord]

    @property
    def evaluation_count(self) -> int:
        """
        Return the number of evaluations in this execution history.
        """

        return len(self.records)

    def metric_trend(
        self,
        metric_name: str,
    ) -> EvaluationMetricTrend:
        """
        Build a metric-specific trend from the execution history.
        """

        return EvaluationMetricTrend(
            metric_name=metric_name,
            points=[
                EvaluationMetricTrendPoint(
                    evaluation_id=record.evaluation_id,
                    execution_id=record.execution_id,
                    evaluator_type=record.evaluator_type,
                    evaluator_version=record.evaluator_version,
                    metric_value=metric.metric_value,
                    explanation=metric.explanation,
                )
                for record in self.records
                for metric in record.metrics
                if metric.metric_name == metric_name
            ],
        )
