from __future__ import annotations

import pytest

from kavach.databases.postgres.cli import migration_dsns_from_environment


def test_migration_dsns_are_pipe_delimited(monkeypatch) -> None:
    monkeypatch.setenv(
        "KAVACH_POSTGRES_MIGRATION_DSNS",
        "postgresql://platform@db/kavach_platform | postgresql://audit@db/kavach_audit",
    )

    assert migration_dsns_from_environment() == (
        "postgresql://platform@db/kavach_platform",
        "postgresql://audit@db/kavach_audit",
    )


def test_migration_requires_at_least_one_dsn(monkeypatch) -> None:
    monkeypatch.delenv("KAVACH_POSTGRES_MIGRATION_DSNS", raising=False)

    with pytest.raises(ValueError, match="KAVACH_POSTGRES_MIGRATION_DSNS"):
        migration_dsns_from_environment()
