from datetime import UTC, datetime
from pathlib import Path

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.domain.models import ModelStatus
from kavach.repositories.sqlite.sqlite_model_repository import (
    SQLiteModelRepository,
)
from kavach.services.models import ModelRegistryService


def test_sqlite_model_registry_service_persists_model_lifecycle(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "kavach.db")
    database.initialize()
    repository = SQLiteModelRepository(database)
    service = ModelRegistryService(
        model_repository=repository,
        id_generator=lambda: "model-1",
        clock=lambda: datetime(2026, 6, 25, tzinfo=UTC),
    )

    model = service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={"temperature": 0.0},
        context_window=128000,
        creator="governance-admin",
    )
    activated = service.activate_model_version(model.model_id)

    reloaded_service = ModelRegistryService(repository)
    reloaded = reloaded_service.get_model(model.model_id)

    assert activated.status == ModelStatus.ACTIVE
    assert reloaded.status == ModelStatus.ACTIVE
    assert reloaded.parameters == {"temperature": 0.0}
