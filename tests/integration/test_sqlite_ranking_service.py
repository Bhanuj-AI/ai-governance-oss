from datetime import UTC, datetime
from pathlib import Path

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationResult,
)
from kavach.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
    Experiment,
    ExperimentCandidate,
    ExperimentStatus,
)
from kavach.domain.models import Model, ModelStatus
from kavach.repositories.sqlite.sqlite_evaluation_repository import (
    SQLiteEvaluationRepository,
)
from kavach.repositories.sqlite.sqlite_evaluation_run_repository import (
    SQLiteEvaluationRunRepository,
)
from kavach.repositories.sqlite.sqlite_experiment_candidate_repository import (
    SQLiteExperimentCandidateRepository,
)
from kavach.repositories.sqlite.sqlite_experiment_repository import (
    SQLiteExperimentRepository,
)
from kavach.repositories.sqlite.sqlite_leaderboard_repository import (
    SQLiteLeaderboardRepository,
)
from kavach.repositories.sqlite.sqlite_model_repository import (
    SQLiteModelRepository,
)
from kavach.services.experiments import RankingService


def test_sqlite_ranking_service_generates_and_persists_leaderboard(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "kavach.db")
    database.initialize()

    experiment_repository = SQLiteExperimentRepository(database)
    candidate_repository = SQLiteExperimentCandidateRepository(database)
    model_repository = SQLiteModelRepository(database)
    evaluation_repository = SQLiteEvaluationRepository(database)
    run_repository = SQLiteEvaluationRunRepository(database)
    leaderboard_repository = SQLiteLeaderboardRepository(database)
    ranking_service = RankingService(
        candidate_repository=candidate_repository,
        evaluation_run_repository=run_repository,
        evaluation_repository=evaluation_repository,
        model_repository=model_repository,
        leaderboard_repository=leaderboard_repository,
        id_generator=lambda: "leaderboard-1",
        clock=lambda: datetime(2026, 6, 27, tzinfo=UTC),
    )

    experiment_repository.save(_experiment())
    candidate_repository.save(_candidate("candidate-1", "model-1"))
    candidate_repository.save(_candidate("candidate-2", "model-2"))
    model_repository.save(_model("model-1", latency=0.8, cost=0.03))
    model_repository.save(_model("model-2", latency=0.5, cost=0.02))
    evaluation_repository.save(
        _result("evaluation-1", "run-1-candidate-1", 0.82, 0.80, 0.10)
    )
    evaluation_repository.save(
        _result("evaluation-2", "run-2-candidate-2", 0.94, 0.93, 0.05)
    )
    run_repository.save(_run("run-1", "candidate-1", "evaluation-1"))
    run_repository.save(_run("run-2", "candidate-2", "evaluation-2"))

    leaderboard = ranking_service.generate_leaderboard("experiment-1")
    reloaded = ranking_service.get_leaderboard("leaderboard-1")

    assert leaderboard == reloaded
    assert [entry.candidate_id for entry in leaderboard.entries] == [
        "candidate-2",
        "candidate-1",
    ]
    assert leaderboard.entries[0].reason == (
        "Ranked by average evaluation metric score."
    )
    assert leaderboard.entries[0].metrics["ANSWER_RELEVANCE"] == 0.93


def _experiment() -> Experiment:
    return Experiment(
        experiment_id="experiment-1",
        name="support-benchmark",
        description="Compare support assistant variants.",
        owner="governance-team",
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
        status=ExperimentStatus.DRAFT,
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


def _run(
    run_id: str,
    candidate_id: str,
    evaluation_result_id: str,
) -> EvaluationRun:
    return EvaluationRun(
        run_id=run_id,
        experiment_id="experiment-1",
        candidate_id=candidate_id,
        dataset_version="2026-06-26",
        evaluation_provider="TruLens",
        evaluation_result_id=evaluation_result_id,
        started_at=datetime(2026, 6, 26, tzinfo=UTC),
        completed_at=datetime(2026, 6, 26, 0, 1, tzinfo=UTC),
        status=EvaluationRunStatus.COMPLETED,
    )
