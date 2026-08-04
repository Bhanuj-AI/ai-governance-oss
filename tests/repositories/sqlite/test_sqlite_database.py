from pathlib import Path

from kavach.databases.sqlite.database import SQLiteDatabase


class TestSQLiteDatabase:
    def test_should_create_schema(
        self,
        tmp_path: Path,
    ) -> None:

        database = SQLiteDatabase(tmp_path / "kavach.db")

        database.initialize()

        with database.connect() as connection:
            cursor = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                """
            )

            tables = {row[0] for row in cursor.fetchall()}

        assert "agent_evaluation" in tables
        assert "dataset_registry" in tables
        assert "evaluation_run" in tables
        assert "experiment" in tables
        assert "experiment_candidate" in tables
        assert "leaderboard" in tables
        assert "leaderboard_entry" in tables
        assert "mcp_execution_audit" in tables
        assert "model_registry" in tables
        assert "prompt_registry" in tables

    def test_should_migrate_legacy_prompt_table_for_withheld_content(
        self,
        tmp_path: Path,
    ) -> None:
        database = SQLiteDatabase(tmp_path / "legacy.db")
        with database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE prompt_registry (
                    prompt_id TEXT NOT NULL PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    template TEXT NOT NULL,
                    variables_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    status TEXT NOT NULL,
                    UNIQUE (name, version)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO prompt_registry VALUES (
                    'legacy-prompt', 'support', 'v1', 'old content', '[]',
                    '2026-07-20T00:00:00+00:00', 'owner', 'ACTIVE'
                )
                """
            )
            connection.commit()

        database.initialize()

        with database.connect() as connection:
            columns = {
                row["name"]: row for row in connection.execute("PRAGMA table_info(prompt_registry)")
            }
            prompt = connection.execute(
                "SELECT template, provenance, content_available FROM prompt_registry"
            ).fetchone()

        assert columns["template"]["notnull"] == 0
        assert {"provenance", "source_system", "content_hash", "content_available"} <= set(columns)
        assert prompt["template"] == "old content"
        assert prompt["provenance"] == "MANAGED"
        assert prompt["content_available"] == 1
