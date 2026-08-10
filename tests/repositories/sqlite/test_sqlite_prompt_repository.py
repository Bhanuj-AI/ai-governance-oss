from pathlib import Path
from datetime import UTC, datetime

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.assets import AssetProvenance
from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.repositories.prompt_repository import PromptRepository
from ai_governance.repositories.sqlite.sqlite_prompt_repository import (
    SQLitePromptRepository,
)
from tests.repositories.contract.test_prompt_repository_contract import (
    PromptRepositoryContract,
)


class TestSQLitePromptRepository(PromptRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        tmp_path: Path,
    ) -> None:
        database = SQLiteDatabase(tmp_path / "ai_governance.db")
        database.initialize()

        self._repository = SQLitePromptRepository(database)

    def repository(self) -> PromptRepository:
        return self._repository

    def test_should_persist_observed_prompt_without_content(self) -> None:
        prompt = Prompt(
            prompt_id="observed-prompt-1",
            name="support-assistant",
            version="v7",
            template=None,
            variables=("question",),
            created_at=datetime(2026, 7, 20, tzinfo=UTC),
            created_by="runtime-agent",
            status=PromptStatus.ACTIVE,
            provenance=AssetProvenance.OBSERVED,
            source_system="evaluation-sdk",
            source_reference="run-123",
            content_hash="sha256:abc123",
            content_available=False,
        )

        self._repository.save(prompt)

        assert self._repository.find_by_id(prompt.prompt_id) == prompt

    def test_tenant_scope_prevents_cross_tenant_prompt_reads(self) -> None:
        """Prompt records are readable only through their persisted scope."""
        prompt = Prompt(
            prompt_id="tenant-prompt",
            name="support-assistant",
            version="v1",
            template="Help {{question}}",
            variables=("question",),
            created_at=datetime(2026, 7, 20, tzinfo=UTC),
            created_by="admin",
            status=PromptStatus.DRAFT,
            tenant_id="tenant-a",
            organization_id="org-a",
            project_id="project-a",
        )
        self._repository.save(prompt)

        assert self._repository.find_by_id(prompt.prompt_id, "org-a", "project-a") == prompt
        assert self._repository.find_by_id(prompt.prompt_id, "org-b", "project-b") is None
