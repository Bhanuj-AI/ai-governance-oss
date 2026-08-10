from datetime import UTC, datetime

import pytest

from ai_governance.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.domain.experiments import ExperimentCandidate
from ai_governance.domain.models import Model, ModelStatus
from ai_governance.services.experiments import (
    AnswerRelevanceRanking,
    GroundednessRanking,
    HallucinationRanking,
    LowestCostRanking,
    LowestLatencyRanking,
    OverallScoreRanking,
)

_UNSET = object()


def test_overall_score_ranking_uses_average_metric_score() -> None:
    score, reason = OverallScoreRanking().score_candidate(
        candidate=_candidate(),
        evaluation_result=_result(
            groundedness=0.90,
            answer_relevance=0.80,
            hallucination=0.10,
        ),
        model=_model(),
    )

    assert score == pytest.approx((0.90 + 0.80 + 0.10) / 3)
    assert reason == "Ranked by average evaluation metric score."


def test_metric_rankings_use_expected_metric() -> None:
    result = _result(
        groundedness=0.92,
        answer_relevance=0.87,
        hallucination=0.08,
    )

    groundedness_score, _ = GroundednessRanking().score_candidate(
        candidate=_candidate(),
        evaluation_result=result,
        model=_model(),
    )
    answer_score, _ = AnswerRelevanceRanking().score_candidate(
        candidate=_candidate(),
        evaluation_result=result,
        model=_model(),
    )
    hallucination_score, _ = HallucinationRanking().score_candidate(
        candidate=_candidate(),
        evaluation_result=result,
        model=_model(),
    )

    assert groundedness_score == pytest.approx(0.92)
    assert answer_score == pytest.approx(0.87)
    assert hallucination_score == pytest.approx(-0.08)


def test_cost_and_latency_rankings_prefer_lower_values() -> None:
    model = _model(
        cost={"input_per_1k": 0.03, "output_per_1k": 0.07},
        latency=0.6,
    )

    cost_score, cost_reason = LowestCostRanking().score_candidate(
        candidate=_candidate(),
        evaluation_result=_result(0.9, 0.8, 0.1),
        model=model,
    )
    latency_score, latency_reason = LowestLatencyRanking().score_candidate(
        candidate=_candidate(),
        evaluation_result=_result(0.9, 0.8, 0.1),
        model=model,
    )

    assert cost_score == pytest.approx(-0.10)
    assert cost_reason == "Ranked by lowest model cost."
    assert latency_score == pytest.approx(-0.6)
    assert latency_reason == "Ranked by lowest model latency."


def test_strategies_raise_when_required_inputs_are_missing() -> None:
    scenarios = [
        (
            GroundednessRanking(),
            _result_without_metric("groundedness"),
            _model(),
            "Ranking strategy requires metric 'GROUNDEDNESS'.",
        ),
        (
            AnswerRelevanceRanking(),
            _result_without_metric("answer_relevance"),
            _model(),
            "Ranking strategy requires metric 'ANSWER_RELEVANCE'.",
        ),
        (
            LowestLatencyRanking(),
            _result(0.9, 0.8, 0.1),
            _model(latency=None),
            "LowestLatencyRanking requires model latency.",
        ),
        (
            LowestCostRanking(),
            _result(0.9, 0.8, 0.1),
            _model(cost=None),
            "LowestCostRanking requires model cost.",
        ),
    ]

    for strategy, result, model, message in scenarios:
        with pytest.raises(ValueError, match=message):
            strategy.score_candidate(
                candidate=_candidate(),
                evaluation_result=result,
                model=model,
            )


def _candidate() -> ExperimentCandidate:
    return ExperimentCandidate(
        candidate_id="candidate-1",
        experiment_id="experiment-1",
        name="Baseline",
        prompt_id="prompt-1",
        prompt_version="v1",
        model_id="model-1",
        model_version="2026-06-26",
        dataset_id="dataset-1",
        dataset_version="2026-06-26",
        evaluation_provider="TruLens",
        temperature=0.0,
        top_p=1.0,
        max_tokens=4096,
        metadata={},
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
    )


def _result(
    groundedness: float,
    answer_relevance: float,
    hallucination: float,
) -> EvaluationResult:
    return EvaluationResult(
        evaluation_id="evaluation-1",
        execution_id="execution-1",
        evaluator_type="FAKE",
        evaluator_version="1.0",
        metrics=[
            EvaluationMetric("GROUNDEDNESS", groundedness),
            EvaluationMetric("ANSWER_RELEVANCE", answer_relevance),
            EvaluationMetric("HALLUCINATION", hallucination),
        ],
        metadata={},
    )


def _result_without_metric(strategy_name: str) -> EvaluationResult:
    metrics = {
        "GROUNDEDNESS": 0.9,
        "ANSWER_RELEVANCE": 0.8,
        "HALLUCINATION": 0.1,
    }
    if strategy_name == "groundedness":
        metrics.pop("GROUNDEDNESS")
    elif strategy_name == "answer_relevance":
        metrics.pop("ANSWER_RELEVANCE")

    return EvaluationResult(
        evaluation_id="evaluation-1",
        execution_id="execution-1",
        evaluator_type="FAKE",
        evaluator_version="1.0",
        metrics=[
            EvaluationMetric(name, value)
            for name, value in metrics.items()
        ],
        metadata={},
    )


def _model(
    cost: dict[str, float] | None | object = _UNSET,
    latency: float | None = 0.4,
) -> Model:
    model_cost = {"input_per_1k": 0.01} if cost is _UNSET else cost

    return Model(
        model_id="model-1",
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-26",
        parameters={"temperature": 0.0},
        cost=model_cost,
        latency=latency,
        context_window=128000,
        creator="model-owner",
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
        status=ModelStatus.ACTIVE,
    )
