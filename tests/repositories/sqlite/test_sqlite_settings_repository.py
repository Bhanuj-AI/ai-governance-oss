import sqlite3
from pathlib import Path

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.settings_control.domain import SettingScope, SettingVersionConflict
from ai_governance.settings_control.repository import SQLiteSettingsRepository


def test_sqlite_settings_repository_versions_and_audits_updates(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "settings.db")
    repository = SQLiteSettingsRepository(database)

    first = repository.save(
        "jobs.retry_attempts", SettingScope.SYSTEM, "", 3, "actor-1", "Initial value", 0
    )
    second = repository.save(
        "jobs.retry_attempts", SettingScope.SYSTEM, "", 5, "actor-2", "Raise retries", 1
    )
    reopened = SQLiteSettingsRepository(database)

    assert first.version == 1
    assert second.version == 2
    assert reopened.get("jobs.retry_attempts", SettingScope.SYSTEM, "").value == 5
    audit = reopened.list_audit("jobs.retry_attempts")
    assert [item.version for item in audit] == [2, 1]
    assert audit[0].old_value == 3
    assert audit[0].new_value == 5
    with pytest.raises(SettingVersionConflict):
        reopened.save(
            "jobs.retry_attempts", SettingScope.SYSTEM, "", 7, "actor-3", "Stale", 1
        )


def test_sqlite_migrates_global_settings_to_system_scope(tmp_path: Path) -> None:
    path = tmp_path / "legacy-settings.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE runtime_setting (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, "
            "version INTEGER NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO runtime_setting VALUES(?,?,?,?,?)",
            (
                "mcp.dry_run_default",
                "true",
                2,
                "legacy-admin",
                "2026-07-10T00:00:00+00:00",
            ),
        )

    repository = SQLiteSettingsRepository(SQLiteDatabase(path))
    migrated = repository.get("mcp.dry_run_default", SettingScope.SYSTEM, "")

    assert migrated is not None
    assert migrated.value is True
    assert migrated.version == 2
