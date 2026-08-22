from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.models import Model, ModelStatus
from ai_governance.repositories.model_repository import ModelRepository
from ai_governance.repositories.sqlite.sqlite_model_repository import (
    SQLiteModelRepository,
)
from tests.repositories.contract.test_model_repository_contract import (
    ModelRepositoryContract,
)


class TestSQLiteModelRepository(ModelRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        tmp_path: Path,
    ) -> None:
        database = SQLiteDatabase(tmp_path / "ai_governance.db")
        database.initialize()

        self._repository = SQLiteModelRepository(database)

    def repository(self) -> ModelRepository:
        return self._repository

    def test_tenant_scope_prevents_cross_tenant_model_reads(self) -> None:
        """Model records are readable only through their persisted scope."""
        model = Model(
            model_id="tenant-model",
            provider="provider",
            model_name="model",
            version="v1",
            parameters={},
            cost=None,
            latency=None,
            context_window=1,
            creator="admin",
            created_at=datetime.now(UTC),
            status=ModelStatus.DRAFT,
            tenant_id="tenant-a",
            organization_id="org-a",
            project_id="project-a",
        )
        self._repository.save(model)

        assert self._repository.find_by_id(model.model_id, "org-a", "project-a") == model
        assert self._repository.find_by_id(model.model_id, "org-b", "project-b") is None
