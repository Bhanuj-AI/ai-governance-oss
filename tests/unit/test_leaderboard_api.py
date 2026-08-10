from datetime import UTC, datetime

from ai_governance.api import LeaderboardAPI
from ai_governance.domain.experiments import (
    Leaderboard,
    LeaderboardEntry,
)
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
from ai_governance.services.experiments import RankingService


def test_leaderboard_api_exposes_framework_neutral_routes() -> None:
    api = _create_api()

    routes = api.routes()

    assert [
        (route.method, route.path, route.handler_name)
        for route in routes
    ] == [
        (
            "GET",
            "/experiments/{experiment}/leaderboard",
            "get_leaderboard",
        ),
        (
            "GET",
            "/experiments/{experiment}/leaderboard/latest",
            "get_latest_leaderboard",
        ),
        (
            "GET",
            "/experiments/{experiment}/recommendation",
            "get_recommendation",
        ),
    ]


def test_leaderboard_api_returns_serializable_leaderboard_payloads() -> None:
    api = _create_api()

    payload = api.get_leaderboard("experiment-1")

    assert len(payload) == 2
    assert payload[0]["leaderboard_id"] == "leaderboard-1"
    assert payload[0]["entries"][0]["candidate_id"] == "candidate-1"
    assert payload[0]["entries"][0]["metrics"]["GROUNDEDNESS"] == 0.91


def test_leaderboard_api_returns_latest_leaderboard_payload() -> None:
    api = _create_api()

    payload = api.get_latest_leaderboard("experiment-1")

    assert payload is not None
    assert payload["leaderboard_id"] == "leaderboard-2"
    assert payload["ranking_strategy"] == "lowest_cost"
    assert payload["entries"][0]["candidate_id"] == "candidate-2"


def test_leaderboard_api_returns_none_when_latest_leaderboard_missing() -> None:
    api = LeaderboardAPI(_create_service())

    assert api.get_latest_leaderboard("missing-experiment") is None


def test_leaderboard_api_returns_recommendation_from_latest_leaderboard() -> None:
    api = _create_api()

    payload = api.get_recommendation("experiment-1")

    assert payload == {
        "recommended_candidate_id": "candidate-2",
        "rank": 1,
        "overall_score": -0.02,
        "ranking_strategy": "lowest_cost",
        "reason": "Ranked by lowest model cost.",
        "leaderboard_id": "leaderboard-2",
        "experiment_id": "experiment-1",
    }


def test_leaderboard_api_returns_none_when_recommendation_missing() -> None:
    api = LeaderboardAPI(_create_service())

    assert api.get_recommendation("missing-experiment") is None


def _create_api() -> LeaderboardAPI:
    repository = InMemoryLeaderboardRepository()
    service = _create_service(repository)
    repository.save(
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
                    metrics={"GROUNDEDNESS": 0.91},
                    cost=0.03,
                    latency=0.6,
                    reason="Ranked by average evaluation metric score.",
                ),
            ),
        )
    )
    repository.save(
        Leaderboard(
            leaderboard_id="leaderboard-2",
            experiment_id="experiment-1",
            ranking_strategy="lowest_cost",
            generated_at=datetime(2026, 6, 27, tzinfo=UTC),
            entries=(
                LeaderboardEntry(
                    rank=1,
                    candidate_id="candidate-2",
                    overall_score=-0.02,
                    metrics={"GROUNDEDNESS": 0.88},
                    cost=0.02,
                    latency=0.5,
                    reason="Ranked by lowest model cost.",
                ),
            ),
        )
    )

    return LeaderboardAPI(service)


def _create_service(
    leaderboard_repository: InMemoryLeaderboardRepository | None = None,
) -> RankingService:
    return RankingService(
        candidate_repository=InMemoryExperimentCandidateRepository(),
        evaluation_run_repository=InMemoryEvaluationRunRepository(),
        evaluation_repository=InMemoryEvaluationRepository(),
        model_repository=InMemoryModelRepository(),
        leaderboard_repository=(
            leaderboard_repository
            if leaderboard_repository is not None
            else InMemoryLeaderboardRepository()
        ),
    )
