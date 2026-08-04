"""Shared SQLite database construction for repository factories."""

from pathlib import Path

from kavach.databases.sqlite.database import SQLiteDatabase


def create_sqlite_database(path: str) -> SQLiteDatabase:
    """Create and initialize the SQLite database used by a repository."""

    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database = SQLiteDatabase(database_path)
    database.initialize()
    return database
