from __future__ import annotations

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.repositories.in_memory.in_memory_job_repository import (
    InMemoryJobRepository,
)
from kavach.repositories.postgres.postgres_job_repository import PostgresJobRepository
from kavach.repositories.sqlite.sqlite_job_repository import SQLiteJobRepository
from kavach.services.dashboard_service import _database_health


def test_database_health_reports_postgres_without_a_sqlite_path() -> None:
    repository = PostgresJobRepository(object())

    assert _database_health(repository) == (
        "Healthy",
        "PostgreSQL persistence is responding.",
    )


def test_database_health_reports_sqlite_path(tmp_path) -> None:
    path = tmp_path / "jobs.db"
    database = SQLiteDatabase(path)
    repository = SQLiteJobRepository(database)

    assert _database_health(repository) == (
        "Healthy",
        f"SQLite persistence is responding ({path}).",
    )


def test_database_health_reports_in_memory_repository() -> None:
    assert _database_health(InMemoryJobRepository()) == (
        "IN MEMORY",
        "Using an in-memory persistence backend.",
    )
