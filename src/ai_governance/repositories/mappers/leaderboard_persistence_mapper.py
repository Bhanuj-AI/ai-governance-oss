from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ai_governance.domain.experiments import (
    Leaderboard,
    LeaderboardEntry,
)


class LeaderboardPersistenceMapper:
    """
    Maps Leaderboard domain objects to and from persistence records.
    """

    @staticmethod
    def to_persistence_records(
        leaderboard: Leaderboard,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        leaderboard_record = {
            "leaderboard_id": leaderboard.leaderboard_id,
            "experiment_id": leaderboard.experiment_id,
            "ranking_strategy": leaderboard.ranking_strategy,
            "generated_at": leaderboard.generated_at.isoformat(),
        }
        entry_records = [
            {
                "leaderboard_id": leaderboard.leaderboard_id,
                "rank": entry.rank,
                "candidate_id": entry.candidate_id,
                "overall_score": entry.overall_score,
                "metrics_json": json.dumps(entry.metrics),
                "cost": entry.cost,
                "latency": entry.latency,
                "reason": entry.reason,
            }
            for entry in leaderboard.entries
        ]

        return leaderboard_record, entry_records

    @staticmethod
    def from_persistence_records(
        leaderboard_record: Mapping[str, Any],
        entry_records: list[Mapping[str, Any]],
    ) -> Leaderboard:
        return Leaderboard(
            leaderboard_id=leaderboard_record["leaderboard_id"],
            experiment_id=leaderboard_record["experiment_id"],
            ranking_strategy=leaderboard_record["ranking_strategy"],
            generated_at=datetime.fromisoformat(
                leaderboard_record["generated_at"]
            ),
            entries=tuple(
                LeaderboardEntry(
                    rank=record["rank"],
                    candidate_id=record["candidate_id"],
                    overall_score=record["overall_score"],
                    metrics=json.loads(record["metrics_json"] or "{}"),
                    cost=record["cost"],
                    latency=record["latency"],
                    reason=record["reason"],
                )
                for record in sorted(
                    entry_records,
                    key=lambda record: record["rank"],
                )
            ),
        )
