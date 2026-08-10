from __future__ import annotations

from datetime import UTC, datetime

from ai_governance.api.mappers import ExperimentApiMapper
from ai_governance.api.models import (
    EvaluationMetricSpecRequest,
    ExperimentCandidateCreateRequest,
)
from ai_governance.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
    Experiment,
    ExperimentCandidate,
    ExperimentStatus,
    Leaderboard,
    LeaderboardEntry,
)


def test_experiment_mapper_scrubs_response_metadata() -> None:
    experiment = Experiment(
        experiment_id="exp-1",
        name="claim-validation",
        description="Compare candidates",
        owner="rest-api",
        created_at=datetime(2026, 6, 27, tzinfo=UTC),
        status=ExperimentStatus.DRAFT,
    )

    response = ExperimentApiMapper.to_experiment_response(
        experiment,
        metadata={"visible": "ok", "api_key": "secret"},
    )

    assert response.experiment_id == "exp-1"
    assert response.status == "DRAFT"
    assert response.metadata == {"visible": "ok"}


def test_candidate_mapper_returns_runtime_parameters_and_scrubbed_metadata() -> None:
    candidate = ExperimentCandidate(
        candidate_id="candidate-1",
        experiment_id="exp-1",
        name="candidate-a",
        prompt_id="prompt",
        prompt_version="v1",
        model_id="model",
        model_version="v1",
        dataset_id="dataset",
        dataset_version="v1",
        evaluation_provider="fake",
        temperature=0.2,
        top_p=0.9,
        max_tokens=256,
        metadata={"visible": "ok", "token": "secret"},
        created_at=datetime(2026, 6, 27, tzinfo=UTC),
    )

    response = ExperimentApiMapper.to_candidate_response(candidate)

    assert response.candidate_name == "candidate-a"
    assert response.runtime_parameters == {
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 256,
    }
    assert response.metadata == {"visible": "ok"}


def test_experiment_metric_specs_map_to_domain_specs() -> None:
    specs = ExperimentApiMapper.to_metric_specs(
        [EvaluationMetricSpecRequest(name="Answer Relevance")]
    )

    assert specs[0].name == "answer_relevance"


def test_candidate_runtime_parameters_apply_defaults() -> None:
    request = ExperimentCandidateCreateRequest(
        candidate_name="candidate-a",
        prompt_version="prompt:v1",
        model_version="model:v1",
        dataset_version="dataset:v1",
        provider_name="fake",
    )

    assert ExperimentApiMapper.candidate_runtime_parameters(request) == {
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 1024,
    }


def test_run_and_leaderboard_responses_map_domain_objects() -> None:
    run = EvaluationRun(
        run_id="run-1",
        experiment_id="exp-1",
        candidate_id="candidate-1",
        dataset_version="v1",
        evaluation_provider="fake",
        evaluation_result_id="eval-1",
        started_at=datetime(2026, 6, 27, tzinfo=UTC),
        completed_at=datetime(2026, 6, 27, 0, 0, 1, tzinfo=UTC),
        status=EvaluationRunStatus.COMPLETED,
    )
    leaderboard = Leaderboard(
        leaderboard_id="leaderboard-1",
        experiment_id="exp-1",
        ranking_strategy="overall_score",
        generated_at=datetime(2026, 6, 27, tzinfo=UTC),
        entries=(
            LeaderboardEntry(
                rank=1,
                candidate_id="candidate-1",
                overall_score=0.9,
                metrics={"answer_relevance": 0.9},
                cost=0.01,
                latency=0.2,
                reason="Highest score.",
            ),
        ),
    )

    response = ExperimentApiMapper.to_run_response(
        experiment_id="exp-1",
        runs=[run],
        leaderboard=leaderboard,
    )

    assert response.runs[0].status == "COMPLETED"
    assert response.leaderboard is not None
    assert response.leaderboard.entries[0].candidate_id == "candidate-1"


def test_evaluation_run_response_maps_domain_run() -> None:
    run = EvaluationRun(
        run_id="run-1",
        experiment_id="exp-1",
        candidate_id="candidate-1",
        dataset_version="v1",
        evaluation_provider="fake",
        evaluation_result_id=None,
        started_at=datetime(2026, 6, 27, tzinfo=UTC),
        completed_at=datetime(2026, 6, 27, 0, 0, 1, tzinfo=UTC),
        status=EvaluationRunStatus.FAILED,
    )

    response = ExperimentApiMapper.to_evaluation_run_response(run)

    assert response.run_id == "run-1"
    assert response.provider_name == "fake"
    assert response.status == "FAILED"
