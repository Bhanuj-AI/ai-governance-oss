from __future__ import annotations

from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.experiments import Leaderboard
from ai_governance.repositories.leaderboard_repository import LeaderboardRepository
from ai_governance.repositories.mappers.leaderboard_persistence_mapper import (
    LeaderboardPersistenceMapper,
)
from ai_governance.repositories.postgres._record_adapter import with_jsonb_fields


@final
class PostgresLeaderboardRepository(LeaderboardRepository):
    """
    PostgreSQL implementation of the LeaderboardRepository contract.
    """

    _INSERT_LEADERBOARD_SQL = """
    INSERT INTO leaderboard (
        leaderboard_id,
        experiment_id,
        ranking_strategy,
        generated_at
    )
    VALUES (
        %(leaderboard_id)s,
        %(experiment_id)s,
        %(ranking_strategy)s,
        %(generated_at)s
    )
    ON CONFLICT (leaderboard_id)
    DO UPDATE SET
        experiment_id = EXCLUDED.experiment_id,
        ranking_strategy = EXCLUDED.ranking_strategy,
        generated_at = EXCLUDED.generated_at
    """

    _INSERT_ENTRY_SQL = """
    INSERT INTO leaderboard_entry (
        leaderboard_id,
        rank,
        candidate_id,
        overall_score,
        metrics_json,
        cost,
        latency,
        reason
    )
    VALUES (
        %(leaderboard_id)s,
        %(rank)s,
        %(candidate_id)s,
        %(overall_score)s,
        %(metrics_json)s,
        %(cost)s,
        %(latency)s,
        %(reason)s
    )
    ON CONFLICT (leaderboard_id, rank)
    DO UPDATE SET
        candidate_id = EXCLUDED.candidate_id,
        overall_score = EXCLUDED.overall_score,
        metrics_json = EXCLUDED.metrics_json,
        cost = EXCLUDED.cost,
        latency = EXCLUDED.latency,
        reason = EXCLUDED.reason
    """

    _SELECT_LEADERBOARD_SQL = """
    SELECT
        leaderboard_id,
        experiment_id,
        ranking_strategy,
        generated_at::text AS generated_at
    FROM leaderboard
    """

    _SELECT_ENTRY_SQL = """
    SELECT
        leaderboard_id,
        rank,
        candidate_id,
        overall_score,
        metrics_json::text AS metrics_json,
        cost,
        latency,
        reason
    FROM leaderboard_entry
    """

    def __init__(
        self,
        database: PostgresDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        leaderboard: Leaderboard,
    ) -> None:
        leaderboard_record, entry_records = (
            LeaderboardPersistenceMapper.to_persistence_records(leaderboard)
        )
        adapted_entry_records = [
            with_jsonb_fields(record, "metrics_json")
            for record in entry_records
        ]

        with self._database.connect() as connection:
            try:
                connection.execute(
                    self._INSERT_LEADERBOARD_SQL,
                    leaderboard_record,
                )
                connection.execute(
                    "DELETE FROM leaderboard_entry "
                    "WHERE leaderboard_id = %(leaderboard_id)s",
                    {"leaderboard_id": leaderboard.leaderboard_id},
                )
                with connection.cursor() as cursor:
                    cursor.executemany(
                        self._INSERT_ENTRY_SQL,
                        adapted_entry_records,
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        leaderboard_id: str,
    ) -> Leaderboard | None:
        with self._database.connect() as connection:
            leaderboard_row = connection.execute(
                f"{self._SELECT_LEADERBOARD_SQL} "
                "WHERE leaderboard_id = %(leaderboard_id)s",
                {"leaderboard_id": leaderboard_id},
            ).fetchone()

            if leaderboard_row is None:
                return None

            entry_rows = connection.execute(
                f"{self._SELECT_ENTRY_SQL} "
                "WHERE leaderboard_id = %(leaderboard_id)s "
                "ORDER BY rank",
                {"leaderboard_id": leaderboard_id},
            ).fetchall()

        return LeaderboardPersistenceMapper.from_persistence_records(
            leaderboard_row,
            entry_rows,
        )

    def find_by_experiment_id(
        self,
        experiment_id: str,
    ) -> list[Leaderboard]:
        with self._database.connect() as connection:
            leaderboard_rows = connection.execute(
                f"{self._SELECT_LEADERBOARD_SQL} "
                "WHERE experiment_id = %(experiment_id)s "
                "ORDER BY generated_at, leaderboard_id",
                {"experiment_id": experiment_id},
            ).fetchall()

        return [
            leaderboard
            for row in leaderboard_rows
            if row["leaderboard_id"] is not None
            for leaderboard in [self.find_by_id(row["leaderboard_id"])]
            if leaderboard is not None
        ]

    def find_all(self) -> list[Leaderboard]:
        with self._database.connect() as connection:
            leaderboard_rows = connection.execute(
                f"{self._SELECT_LEADERBOARD_SQL} "
                "ORDER BY experiment_id, generated_at, leaderboard_id"
            ).fetchall()

        return [
            leaderboard
            for row in leaderboard_rows
            if row["leaderboard_id"] is not None
            for leaderboard in [self.find_by_id(row["leaderboard_id"])]
            if leaderboard is not None
        ]
