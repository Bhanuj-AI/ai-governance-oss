from datetime import UTC, datetime

import pytest

from kavach.domain.experiments import (
    CandidateRanking,
    ExperimentCandidate,
    Leaderboard,
    LeaderboardEntry,
)


def test_leaderboard_entry_copies_metrics() -> None:
    metrics = {"GROUNDEDNESS": 0.91}

    entry = LeaderboardEntry(
        rank=1,
        candidate_id="candidate-1",
        overall_score=0.91,
        metrics=metrics,
        cost=0.01,
        latency=0.4,
        reason="Ranked by groundedness.",
    )
    metrics["GROUNDEDNESS"] = 0.0

    assert entry.metrics == {"GROUNDEDNESS": 0.91}


def test_leaderboard_requires_consecutive_ranks() -> None:
    with pytest.raises(ValueError):
        Leaderboard(
            leaderboard_id="leaderboard-1",
            experiment_id="experiment-1",
            ranking_strategy="overall_score",
            generated_at=datetime(2026, 6, 26, tzinfo=UTC),
            entries=(
                LeaderboardEntry(
                    rank=1,
                    candidate_id="candidate-1",
                    overall_score=0.91,
                    metrics={},
                    cost=None,
                    latency=None,
                    reason="Top candidate.",
                ),
                LeaderboardEntry(
                    rank=3,
                    candidate_id="candidate-2",
                    overall_score=0.85,
                    metrics={},
                    cost=None,
                    latency=None,
                    reason="Second candidate.",
                ),
            ),
        )


def test_candidate_ranking_rejects_negative_rank() -> None:
    with pytest.raises(ValueError):
        CandidateRanking(
            experiment_id="experiment-1",
            candidate=_candidate("candidate-1", "model-1"),
            evaluation_run_id="run-1",
            evaluation_result_id="evaluation-1",
            overall_score=0.91,
            rank=-1,
        )


def _candidate(
    candidate_id: str,
    model_id: str,
) -> ExperimentCandidate:
    return ExperimentCandidate(
        candidate_id=candidate_id,
        experiment_id="experiment-1",
        name=candidate_id,
        prompt_id="prompt-1",
        prompt_version="v1",
        model_id=model_id,
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
