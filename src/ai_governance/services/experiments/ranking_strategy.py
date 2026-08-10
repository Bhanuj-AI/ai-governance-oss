from __future__ import annotations

from abc import ABC, abstractmethod

from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.domain.experiments import ExperimentCandidate
from ai_governance.domain.models import Model


class RankingStrategy(ABC):
    """
    Strategy for scoring candidates for leaderboard generation.
    """

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        pass

    @abstractmethod
    def score_candidate(
        self,
        candidate: ExperimentCandidate,
        evaluation_result: EvaluationResult,
        model: Model | None,
    ) -> tuple[float, str]:
        pass


class OverallScoreRanking(RankingStrategy):
    @property
    def strategy_name(self) -> str:
        return "overall_score"

    def score_candidate(
        self,
        candidate: ExperimentCandidate,
        evaluation_result: EvaluationResult,
        model: Model | None,
    ) -> tuple[float, str]:
        if not evaluation_result.metrics:
            raise ValueError("OverallScoreRanking requires evaluation metrics.")

        score = sum(
            metric.metric_value
            for metric in evaluation_result.metrics
        ) / len(evaluation_result.metrics)

        return score, "Ranked by average evaluation metric score."


class GroundednessRanking(RankingStrategy):
    @property
    def strategy_name(self) -> str:
        return "groundedness"

    def score_candidate(
        self,
        candidate: ExperimentCandidate,
        evaluation_result: EvaluationResult,
        model: Model | None,
    ) -> tuple[float, str]:
        score = _metric_value(evaluation_result, "GROUNDEDNESS")
        return score, "Ranked by GROUNDEDNESS metric."


class AnswerRelevanceRanking(RankingStrategy):
    @property
    def strategy_name(self) -> str:
        return "answer_relevance"

    def score_candidate(
        self,
        candidate: ExperimentCandidate,
        evaluation_result: EvaluationResult,
        model: Model | None,
    ) -> tuple[float, str]:
        score = _metric_value(evaluation_result, "ANSWER_RELEVANCE")
        return score, "Ranked by ANSWER_RELEVANCE metric."


class LowestLatencyRanking(RankingStrategy):
    @property
    def strategy_name(self) -> str:
        return "lowest_latency"

    def score_candidate(
        self,
        candidate: ExperimentCandidate,
        evaluation_result: EvaluationResult,
        model: Model | None,
    ) -> tuple[float, str]:
        if model is None or model.latency is None:
            raise ValueError("LowestLatencyRanking requires model latency.")

        return -model.latency, "Ranked by lowest model latency."


class LowestCostRanking(RankingStrategy):
    @property
    def strategy_name(self) -> str:
        return "lowest_cost"

    def score_candidate(
        self,
        candidate: ExperimentCandidate,
        evaluation_result: EvaluationResult,
        model: Model | None,
    ) -> tuple[float, str]:
        if model is None or model.cost is None:
            raise ValueError("LowestCostRanking requires model cost.")

        return -sum(model.cost.values()), "Ranked by lowest model cost."


class HallucinationRanking(RankingStrategy):
    @property
    def strategy_name(self) -> str:
        return "hallucination"

    def score_candidate(
        self,
        candidate: ExperimentCandidate,
        evaluation_result: EvaluationResult,
        model: Model | None,
    ) -> tuple[float, str]:
        score = _metric_value(evaluation_result, "HALLUCINATION")
        return -score, "Ranked by lowest HALLUCINATION metric."


def _metric_value(
    evaluation_result: EvaluationResult,
    metric_name: str,
) -> float:
    for metric in evaluation_result.metrics:
        if metric.metric_name == metric_name:
            return metric.metric_value

    raise ValueError(
        f"Ranking strategy requires metric '{metric_name}'."
    )
