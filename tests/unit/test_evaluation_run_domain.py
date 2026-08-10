from datetime import UTC, datetime

import pytest

from ai_governance.domain.experiments import (
    CandidateRanking,
    EvaluationRun,
    EvaluationRunStatus,
    ExperimentCandidate,
)


def test_completed_evaluation_run_requires_result_id() -> None:
    with pytest.raises(ValueError):
        EvaluationRun(
            run_id="run-1",
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            dataset_version="2026-06-26",
            evaluation_provider="TruLens",
            evaluation_result_id=None,
            started_at=datetime(2026, 6, 26, tzinfo=UTC),
            completed_at=datetime(2026, 6, 26, 0, 1, tzinfo=UTC),
            status=EvaluationRunStatus.COMPLETED,
        )


def test_candidate_ranking_keeps_candidate_reference() -> None:
    candidate = ExperimentCandidate(
        candidate_id="candidate-1",
        experiment_id="experiment-1",
        name="Baseline",
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
    )

    ranking = CandidateRanking(
        experiment_id="experiment-1",
        candidate=candidate,
        evaluation_run_id="run-1",
        evaluation_result_id="evaluation-1",
        overall_score=0.95,
        rank=1,
    )

    assert ranking.candidate == candidate
