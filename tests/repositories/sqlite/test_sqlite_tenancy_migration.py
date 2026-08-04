from __future__ import annotations


from kavach.databases.sqlite.database import SQLiteDatabase


def test_legacy_rows_are_backfilled_idempotently(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    database = SQLiteDatabase(path)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO job_execution (job_id, job_type, status, input_refs_json, "
            "input_hash, idempotency_key, submitted_by, attempt_count, max_attempts, "
            "created_at, updated_at) VALUES "
            "('job_1', 'EVALUATION', 'QUEUED', '{}', 'hash', 'key', 'actor', 0, 3, "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
    monkeypatch.setenv("KAVACH_BOOTSTRAP_ORGANIZATION_ID", "org_migrated")
    monkeypatch.setenv("KAVACH_BOOTSTRAP_PROJECT_ID", "project_migrated")
    database.initialize()
    database.initialize()
    with database.connect() as connection:
        row = connection.execute(
            "SELECT organization_id, project_id FROM job_execution WHERE job_id='job_1'"
        ).fetchone()
        assert tuple(row) == ("org_migrated", "project_migrated")


def test_new_operational_rows_receive_bootstrap_scope(tmp_path):
    database = SQLiteDatabase(tmp_path / "new.db")
    database.initialize()
    with database.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(job_execution)")
        }
    assert {"organization_id", "project_id"} <= columns
