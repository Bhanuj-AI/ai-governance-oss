from __future__ import annotations

from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.experiments import Leaderboard
from ai_governance.repositories.leaderboard_repository import LeaderboardRepository
from ai_governance.repositories.mappers.leaderboard_persistence_mapper import (
    LeaderboardPersistenceMapper,
)


@final
class SQLiteLeaderboardRepository(LeaderboardRepository):
    """
    SQLite implementation of the LeaderboardRepository contract.
    """

    _INSERT_LEADERBOARD_SQL = """
    INSERT OR REPLACE INTO leaderboard (
        leaderboard_id,
        experiment_id,
        ranking_strategy,
        generated_at
    )
    VALUES (
        :leaderboard_id,
        :experiment_id,
        :ranking_strategy,
        :generated_at
    )
    """

    _INSERT_ENTRY_SQL = """
    INSERT OR REPLACE INTO leaderboard_entry (
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
        :leaderboard_id,
        :rank,
        :candidate_id,
        :overall_score,
        :metrics_json,
        :cost,
        :latency,
        :reason
    )
    """

    _SELECT_LEADERBOARD_SQL = """
    SELECT
        leaderboard_id,
        experiment_id,
        ranking_strategy,
        generated_at
    FROM leaderboard
    """

    _SELECT_ENTRY_SQL = """
    SELECT
        leaderboard_id,
        rank,
        candidate_id,
        overall_score,
        metrics_json,
        cost,
        latency,
        reason
    FROM leaderboard_entry
    """

    def __init__(
        self,
        database: SQLiteDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        leaderboard: Leaderboard,
    ) -> None:
        leaderboard_record, entry_records = (
            LeaderboardPersistenceMapper.to_persistence_records(leaderboard)
        )

        with self._database.connect() as connection:
            try:
                connection.execute(
                    self._INSERT_LEADERBOARD_SQL,
                    leaderboard_record,
                )
                connection.execute(
                    "DELETE FROM leaderboard_entry WHERE leaderboard_id = ?",
                    (leaderboard.leaderboard_id,),
                )
                connection.executemany(
                    self._INSERT_ENTRY_SQL,
                    entry_records,
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
                f"{self._SELECT_LEADERBOARD_SQL} WHERE leaderboard_id = ?",
                (leaderboard_id,),
            ).fetchone()

            if leaderboard_row is None:
                return None

            entry_rows = connection.execute(
                f"{self._SELECT_ENTRY_SQL} "
                "WHERE leaderboard_id = ? "
                "ORDER BY rank",
                (leaderboard_id,),
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
                "WHERE experiment_id = ? "
                "ORDER BY generated_at, leaderboard_id",
                (experiment_id,),
            ).fetchall()

        return [
            self.find_by_id(row["leaderboard_id"])
            for row in leaderboard_rows
            if row["leaderboard_id"] is not None
        ]

    def find_all(self) -> list[Leaderboard]:
        with self._database.connect() as connection:
            leaderboard_rows = connection.execute(
                f"{self._SELECT_LEADERBOARD_SQL} "
                "ORDER BY experiment_id, generated_at, leaderboard_id"
            ).fetchall()

        return [
            self.find_by_id(row["leaderboard_id"])
            for row in leaderboard_rows
            if row["leaderboard_id"] is not None
        ]
