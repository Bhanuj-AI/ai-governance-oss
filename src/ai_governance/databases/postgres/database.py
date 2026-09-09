from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg.rows import dict_row

_SCHEMA_INITIALIZATION_LOCK = 278_460_749


class PostgresDatabase:
    """
    Lightweight PostgreSQL wrapper responsible only for:

    - opening connections
    - initializing schema
    - transaction management

    Repository classes own all domain-specific SQL.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    @property
    def dsn(self) -> str:
        return self._dsn

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(
            self._dsn,
            row_factory=dict_row,
        )

    def initialize(self) -> None:
        schema_path = Path(__file__).parent.joinpath("schema.sql")
        schema = schema_path.read_text(encoding="utf-8")

        with self.connect() as connection:
            # Repository factories may initialize concurrently across API,
            # worker, and migration processes. CREATE ... IF NOT EXISTS still
            # takes conflicting DDL locks, so serialize the whole schema pass.
            connection.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_SCHEMA_INITIALIZATION_LOCK,),
            )
            connection.execute(schema)
            connection.execute(
                "ALTER TABLE evaluation_run "
                "ADD COLUMN IF NOT EXISTS failure_reason TEXT"
            )
            connection.execute(
                "ALTER TABLE evaluation_run "
                "ADD COLUMN IF NOT EXISTS total_item_count INTEGER"
            )
            connection.execute(
                "ALTER TABLE evaluation_run "
                "ADD COLUMN IF NOT EXISTS completed_item_count INTEGER NOT NULL DEFAULT 0"
            )
            connection.execute(
                "ALTER TABLE evaluation_run "
                "ADD COLUMN IF NOT EXISTS evaluated_item_count INTEGER NOT NULL DEFAULT 0"
            )
            connection.execute(
                "ALTER TABLE evaluation_run "
                "ADD COLUMN IF NOT EXISTS runner_provenance_json JSONB"
            )
            connection.commit()
