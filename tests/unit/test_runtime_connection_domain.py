from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.domain.runtime_connection import RuntimeConnection


def test_runtime_connection_rejects_raw_secret_values_in_settings() -> None:
    with pytest.raises(ValueError, match="must not contain secrets"):
        RuntimeConnection(
            runtime_connection_id="connection-1",
            display_name="Unsafe",
            provider="openai",
            settings={"api_key": "raw-secret"},
            secret_refs={"api_key": "env://OPENAI_API_KEY"},
            enabled=True,
            organization_id="org-a",
            project_id="project-a",
            created_by="actor",
            updated_by="actor",
            created_at=datetime(2026, 8, 11, tzinfo=UTC),
            updated_at=datetime(2026, 8, 11, tzinfo=UTC),
        )
