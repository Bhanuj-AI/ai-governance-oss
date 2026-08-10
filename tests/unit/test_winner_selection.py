from datetime import UTC, datetime

from ai_governance.domain.experiments import (
    CandidateRanking,
    ExperimentCandidate,
)
from ai_governance.services.experiments import (
    HighestOverallScoreSelectionStrategy,
)


def test_highest_overall_score_strategy_selects_best_candidate() -> None:
    strategy = HighestOverallScoreSelectionStrategy()
    baseline = _ranking("candidate-1", 0.81, 2)
    winner = _ranking("candidate-2", 0.93, 1)

    selected = strategy.select_winner([baseline, winner])

    assert selected == winner


def _ranking(
    candidate_id: str,
    score: float,
    rank: int,
) -> CandidateRanking:
    return CandidateRanking(
        experiment_id="experiment-1",
        candidate=ExperimentCandidate(
            candidate_id=candidate_id,
            experiment_id="experiment-1",
            name=candidate_id,
            prompt_id="prompt-1",
            prompt_version="v1",
            model_id="model-1",
            model_version="2026-06-25",
            dataset_id="dataset-1",
            dataset_version="2026-06-26",
            evaluation_provider="TruLens",
            temperature=0.0,
            top_p=1.0,
            max_tokens=4096,
            metadata={},
            created_at=datetime(2026, 6, 26, tzinfo=UTC),
        ),
        evaluation_run_id=f"run-{candidate_id}",
        evaluation_result_id=f"evaluation-{candidate_id}",
        overall_score=score,
        rank=rank,
    )
