from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
    ExperimentCandidate,
)
from ai_governance.domain.models import Model, ModelStatus
from ai_governance.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from ai_governance.repositories.in_memory_evaluation_run_repository import (
    InMemoryEvaluationRunRepository,
)
from ai_governance.repositories.in_memory_experiment_candidate_repository import (
    InMemoryExperimentCandidateRepository,
)
from ai_governance.repositories.in_memory_leaderboard_repository import (
    InMemoryLeaderboardRepository,
)
from ai_governance.repositories.in_memory_model_repository import (
    InMemoryModelRepository,
)
from ai_governance.services.experiments import RankingError, RankingService


def test_ranking_service_ranks_candidates_and_generates_leaderboard() -> None:
    dependencies = _dependencies()
    ranking_service = RankingService(
        candidate_repository=dependencies["candidate_repository"],
        evaluation_run_repository=dependencies["run_repository"],
        evaluation_repository=dependencies["evaluation_repository"],
        model_repository=dependencies["model_repository"],
        leaderboard_repository=dependencies["leaderboard_repository"],
        id_generator=lambda: "leaderboard-1",
        clock=lambda: datetime(2026, 6, 27, tzinfo=UTC),
    )

    baseline = _candidate("candidate-1", "model-1")
    improved = _candidate("candidate-2", "model-2")
    dependencies["candidate_repository"].save(baseline)
    dependencies["candidate_repository"].save(improved)
    dependencies["model_repository"].save(
        _model("model-1", latency=0.7, cost=0.03)
    )
    dependencies["model_repository"].save(
        _model("model-2", latency=0.4, cost=0.02)
    )
    dependencies["evaluation_repository"].save(
        _result("evaluation-1", "run-1-candidate-1", 0.81, 0.79, 0.11)
    )
    dependencies["evaluation_repository"].save(
        _result("evaluation-2", "run-2-candidate-2", 0.93, 0.95, 0.04)
    )
    dependencies["run_repository"].save(
        _completed_run("run-1", baseline.candidate_id, "evaluation-1")
    )
    dependencies["run_repository"].save(
        _completed_run("run-2", improved.candidate_id, "evaluation-2")
    )

    rankings = ranking_service.rank_candidates("experiment-1")
    leaderboard = ranking_service.generate_leaderboard("experiment-1")

    assert [ranking.candidate.candidate_id for ranking in rankings] == [
        "candidate-2",
        "candidate-1",
    ]
    assert rankings[0].rank == 1
    assert rankings[0].reason == "Ranked by average evaluation metric score."
    assert leaderboard.entries[0].candidate_id == "candidate-2"
    assert leaderboard.entries[0].metrics["GROUNDEDNESS"] == pytest.approx(
        0.93
    )
    assert leaderboard.entries[0].cost == pytest.approx(0.02)
    assert leaderboard.entries[0].latency == pytest.approx(0.4)
    assert dependencies["leaderboard_repository"].find_by_id(
        "leaderboard-1"
    ) == leaderboard


def test_ranking_service_uses_latest_completed_run_per_candidate() -> None:
    dependencies = _dependencies()
    ranking_service = RankingService(
        candidate_repository=dependencies["candidate_repository"],
        evaluation_run_repository=dependencies["run_repository"],
        evaluation_repository=dependencies["evaluation_repository"],
        model_repository=dependencies["model_repository"],
        leaderboard_repository=dependencies["leaderboard_repository"],
    )
    candidate = _candidate("candidate-1", "model-1")
    dependencies["candidate_repository"].save(candidate)
    dependencies["model_repository"].save(
        _model("model-1", latency=0.5, cost=0.01)
    )
    dependencies["evaluation_repository"].save(
        _result("evaluation-old", "run-old-candidate-1", 0.75, 0.75, 0.12)
    )
    dependencies["evaluation_repository"].save(
        _result("evaluation-new", "run-new-candidate-1", 0.91, 0.89, 0.07)
    )
    dependencies["run_repository"].save(
        _completed_run(
            "run-old",
            candidate.candidate_id,
            "evaluation-old",
            completed_at=datetime(2026, 6, 26, 0, 5, tzinfo=UTC),
        )
    )
    dependencies["run_repository"].save(
        _completed_run(
            "run-new",
            candidate.candidate_id,
            "evaluation-new",
            completed_at=datetime(2026, 6, 26, 0, 10, tzinfo=UTC),
        )
    )
    dependencies["run_repository"].save(
        EvaluationRun(
            run_id="run-pending",
            experiment_id="experiment-1",
            candidate_id=candidate.candidate_id,
            dataset_version="2026-06-26",
            evaluation_provider="TruLens",
            evaluation_result_id=None,
            started_at=None,
            completed_at=None,
            status=EvaluationRunStatus.PENDING,
        )
    )

    top_candidate = ranking_service.top_candidate("experiment-1")

    assert top_candidate.evaluation_run_id == "run-new"
    assert top_candidate.evaluation_result_id == "evaluation-new"


def test_ranking_service_rejects_missing_completed_runs() -> None:
    dependencies = _dependencies()
    ranking_service = RankingService(
        candidate_repository=dependencies["candidate_repository"],
        evaluation_run_repository=dependencies["run_repository"],
        evaluation_repository=dependencies["evaluation_repository"],
        model_repository=dependencies["model_repository"],
        leaderboard_repository=dependencies["leaderboard_repository"],
    )
    candidate = _candidate("candidate-1", "model-1")
    dependencies["candidate_repository"].save(candidate)

    with pytest.raises(
        RankingError,
        match="Only completed evaluation runs participate in ranking.",
    ):
        ranking_service.rank_candidates("experiment-1")


def _dependencies() -> dict[str, object]:
    return {
        "candidate_repository": InMemoryExperimentCandidateRepository(),
        "run_repository": InMemoryEvaluationRunRepository(),
        "evaluation_repository": InMemoryEvaluationRepository(),
        "model_repository": InMemoryModelRepository(),
        "leaderboard_repository": InMemoryLeaderboardRepository(),
    }


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


def _model(
    model_id: str,
    latency: float,
    cost: float,
) -> Model:
    return Model(
        model_id=model_id,
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-26",
        parameters={"temperature": 0.0},
        cost={"input_per_1k": cost},
        latency=latency,
        context_window=128000,
        creator="model-owner",
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
        status=ModelStatus.ACTIVE,
    )


def _result(
    evaluation_id: str,
    execution_id: str,
    groundedness: float,
    answer_relevance: float,
    hallucination: float,
) -> EvaluationResult:
    return EvaluationResult(
        evaluation_id=evaluation_id,
        execution_id=execution_id,
        evaluator_type="FAKE",
        evaluator_version="1.0",
        metrics=[
            EvaluationMetric("GROUNDEDNESS", groundedness),
            EvaluationMetric("ANSWER_RELEVANCE", answer_relevance),
            EvaluationMetric("HALLUCINATION", hallucination),
        ],
        metadata={},
    )


def _completed_run(
    run_id: str,
    candidate_id: str,
    evaluation_result_id: str,
    completed_at: datetime | None = None,
) -> EvaluationRun:
    start = datetime(2026, 6, 26, tzinfo=UTC)
    end = completed_at or datetime(2026, 6, 26, 0, 1, tzinfo=UTC)

    return EvaluationRun(
        run_id=run_id,
        experiment_id="experiment-1",
        candidate_id=candidate_id,
        dataset_version="2026-06-26",
        evaluation_provider="TruLens",
        evaluation_result_id=evaluation_result_id,
        started_at=start,
        completed_at=end,
        status=EvaluationRunStatus.COMPLETED,
    )
