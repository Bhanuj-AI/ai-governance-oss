from __future__ import annotations

from pathlib import Path

from kavach.databases.sqlite.database import SQLiteDatabase

from .postgres_repository import PostgresControlPlaneRepository
from .repository import InMemoryControlPlaneRepository
from .sqlite_repository import SQLiteControlPlaneRepository


class ControlPlaneRepositoryFactory:
    @staticmethod
    def create(
        backend: str, *, sqlite_path: str | None = None, postgres_dsn: str | None = None
    ):
        normalized = backend.strip().lower()
        if normalized == "inmemory":
            return InMemoryControlPlaneRepository()
        if normalized == "sqlite":
            if not sqlite_path:
                raise ValueError(
                    "sqlite_path is required for the SQLite tenancy backend"
                )
            return SQLiteControlPlaneRepository(SQLiteDatabase(Path(sqlite_path)))
        if normalized == "postgres":
            if not postgres_dsn:
                raise ValueError(
                    "postgres_dsn is required for the PostgreSQL tenancy backend"
                )
            return PostgresControlPlaneRepository(postgres_dsn)
        raise ValueError(f"Unsupported tenancy repository backend: {backend}")
