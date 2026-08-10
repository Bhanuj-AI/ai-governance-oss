from __future__ import annotations

import pytest

from ai_governance.databases.postgres.cli import migration_dsns_from_environment


def test_migration_dsns_are_pipe_delimited(monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_GOVERNANCE_POSTGRES_MIGRATION_DSNS",
        "postgresql://platform@db/ai_governance_platform | postgresql://audit@db/ai_governance_audit",
    )

    assert migration_dsns_from_environment() == (
        "postgresql://platform@db/ai_governance_platform",
        "postgresql://audit@db/ai_governance_audit",
    )


def test_migration_requires_at_least_one_dsn(monkeypatch) -> None:
    monkeypatch.delenv("AI_GOVERNANCE_POSTGRES_MIGRATION_DSNS", raising=False)

    with pytest.raises(ValueError, match="AI_GOVERNANCE_POSTGRES_MIGRATION_DSNS"):
        migration_dsns_from_environment()
