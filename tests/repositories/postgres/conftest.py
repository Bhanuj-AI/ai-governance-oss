from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from ai_governance.databases.postgres.database import PostgresDatabase


@pytest.fixture
def postgres_database() -> Iterator[PostgresDatabase]:
    dsn = os.getenv("AI_GOVERNANCE_POSTGRES_DSN")

    if not dsn:
        pytest.skip("AI_GOVERNANCE_POSTGRES_DSN is not set")

    schema_name = f"ai_governance_test_{uuid4().hex}"

    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(
                sql.Identifier(schema_name),
            )
        )

    database = PostgresDatabase(
        make_conninfo(
            dsn,
            options=f"-c search_path={schema_name}",
        )
    )
    database.initialize()

    try:
        yield database
    finally:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema_name),
                )
            )
