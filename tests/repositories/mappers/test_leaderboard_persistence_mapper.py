from datetime import UTC, datetime

from kavach.domain.experiments import (
    Leaderboard,
    LeaderboardEntry,
)
from kavach.repositories.mappers.leaderboard_persistence_mapper import (
    LeaderboardPersistenceMapper,
)


def test_leaderboard_persistence_mapper_round_trips_leaderboard() -> None:
    leaderboard = Leaderboard(
        leaderboard_id="leaderboard-1",
        experiment_id="experiment-1",
        ranking_strategy="overall_score",
        generated_at=datetime(2026, 6, 26, tzinfo=UTC),
        entries=(
            LeaderboardEntry(
                rank=1,
                candidate_id="candidate-1",
                overall_score=0.94,
                metrics={"GROUNDEDNESS": 0.95},
                cost=0.02,
                latency=0.4,
                reason="Top candidate.",
            ),
        ),
    )

    leaderboard_record, entry_records = (
        LeaderboardPersistenceMapper.to_persistence_records(leaderboard)
    )
    reloaded = LeaderboardPersistenceMapper.from_persistence_records(
        leaderboard_record,
        entry_records,
    )

    assert reloaded == leaderboard
