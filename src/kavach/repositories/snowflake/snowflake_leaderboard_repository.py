from __future__ import annotations

from typing import final

from snowflake.connector import DictCursor

from kavach.databases.snowflake.database import SnowflakeDatabase
from kavach.domain.experiments import Leaderboard
from kavach.repositories.leaderboard_repository import LeaderboardRepository
from kavach.repositories.mappers.leaderboard_persistence_mapper import (
    LeaderboardPersistenceMapper,
)
from kavach.repositories.snowflake._record_adapter import (
    lowercase_record,
    lowercase_records,
)


@final
class SnowflakeLeaderboardRepository(LeaderboardRepository):
    """
    Snowflake implementation of the LeaderboardRepository contract.
    """

    _MERGE_LEADERBOARD_SQL = """
    MERGE INTO leaderboard target
    USING (
        SELECT
            %(leaderboard_id)s AS leaderboard_id,
            %(experiment_id)s AS experiment_id,
            %(ranking_strategy)s AS ranking_strategy,
            TO_TIMESTAMP_TZ(%(generated_at)s) AS generated_at
    ) source
    ON target.leaderboard_id = source.leaderboard_id
    WHEN MATCHED THEN UPDATE SET
        experiment_id = source.experiment_id,
        ranking_strategy = source.ranking_strategy,
        generated_at = source.generated_at
    WHEN NOT MATCHED THEN INSERT (
        leaderboard_id,
        experiment_id,
        ranking_strategy,
        generated_at
    )
    VALUES (
        source.leaderboard_id,
        source.experiment_id,
        source.ranking_strategy,
        source.generated_at
    )
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
    SELECT
        %(leaderboard_id)s,
        %(rank)s,
        %(candidate_id)s,
        %(overall_score)s,
        PARSE_JSON(%(metrics_json)s),
        %(cost)s,
        %(latency)s,
        %(reason)s
    """

    _SELECT_LEADERBOARD_SQL = """
    SELECT
        leaderboard_id,
        experiment_id,
        ranking_strategy,
        TO_VARCHAR(generated_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')
            AS generated_at
    FROM leaderboard
    """

    _SELECT_ENTRY_SQL = """
    SELECT
        leaderboard_id,
        rank,
        candidate_id,
        overall_score,
        TO_JSON(metrics_json) AS metrics_json,
        cost,
        latency,
        reason
    FROM leaderboard_entry
    """

    def __init__(
        self,
        database: SnowflakeDatabase,
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
                with connection.cursor() as cursor:
                    cursor.execute(
                        self._MERGE_LEADERBOARD_SQL,
                        leaderboard_record,
                    )
                    cursor.execute(
                        "DELETE FROM leaderboard_entry "
                        "WHERE leaderboard_id = %(leaderboard_id)s",
                        {"leaderboard_id": leaderboard.leaderboard_id},
                    )
                    for entry_record in entry_records:
                        cursor.execute(self._INSERT_ENTRY_SQL, entry_record)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        leaderboard_id: str,
    ) -> Leaderboard | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_LEADERBOARD_SQL} "
                    "WHERE leaderboard_id = %(leaderboard_id)s",
                    {"leaderboard_id": leaderboard_id},
                )
                leaderboard_row = cursor.fetchone()

                if leaderboard_row is None:
                    return None

                cursor.execute(
                    f"{self._SELECT_ENTRY_SQL} "
                    "WHERE leaderboard_id = %(leaderboard_id)s "
                    "ORDER BY rank",
                    {"leaderboard_id": leaderboard_id},
                )
                entry_rows = lowercase_records(cursor.fetchall())

        return LeaderboardPersistenceMapper.from_persistence_records(
            lowercase_record(leaderboard_row),
            entry_rows,
        )

    def find_by_experiment_id(
        self,
        experiment_id: str,
    ) -> list[Leaderboard]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_LEADERBOARD_SQL} "
                    "WHERE experiment_id = %(experiment_id)s "
                    "ORDER BY generated_at, leaderboard_id",
                    {"experiment_id": experiment_id},
                )
                leaderboard_rows = lowercase_records(cursor.fetchall())

        return [
            leaderboard
            for row in leaderboard_rows
            if row["leaderboard_id"] is not None
            for leaderboard in [self.find_by_id(row["leaderboard_id"])]
            if leaderboard is not None
        ]

    def find_all(self) -> list[Leaderboard]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_LEADERBOARD_SQL} "
                    "ORDER BY experiment_id, generated_at, leaderboard_id"
                )
                leaderboard_rows = lowercase_records(cursor.fetchall())

        return [
            leaderboard
            for row in leaderboard_rows
            if row["leaderboard_id"] is not None
            for leaderboard in [self.find_by_id(row["leaderboard_id"])]
            if leaderboard is not None
        ]
