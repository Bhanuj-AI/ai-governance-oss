from datetime import UTC, datetime
from pathlib import Path

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.models import ModelStatus
from ai_governance.repositories.sqlite.sqlite_model_repository import (
    SQLiteModelRepository,
)
from ai_governance.services.models import ModelRegistryService
from ai_governance.tenancy.domain import TenantContext


def test_sqlite_model_registry_service_persists_model_lifecycle(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "ai_governance.db")
    database.initialize()
    repository = SQLiteModelRepository(database)
    service = ModelRegistryService(
        model_repository=repository,
        id_generator=lambda: "model-1",
        clock=lambda: datetime(2026, 6, 25, tzinfo=UTC),
    )
    context = TenantContext(
        "org_default", "project_default", "governance-admin", "test-request"
    )

    model = service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={"temperature": 0.0},
        context_window=128000,
        creator="governance-admin",
        context=context,
    )
    activated = service.activate_model_version(model.model_id, context)

    reloaded_service = ModelRegistryService(repository)
    reloaded = reloaded_service.get_model(model.model_id, context)

    assert activated.status == ModelStatus.ACTIVE
    assert reloaded.status == ModelStatus.ACTIVE
    assert reloaded.parameters == {"temperature": 0.0}
