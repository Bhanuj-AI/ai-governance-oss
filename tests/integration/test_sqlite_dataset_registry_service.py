from datetime import UTC, datetime
from pathlib import Path

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.datasets import DatasetStatus
from ai_governance.repositories.sqlite.sqlite_dataset_repository import (
    SQLiteDatasetRepository,
)
from ai_governance.services.datasets import DatasetRegistryService


def test_sqlite_dataset_registry_service_persists_dataset_lifecycle(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "ai_governance.db")
    database.initialize()
    repository = SQLiteDatasetRepository(database)
    service = DatasetRegistryService(
        dataset_repository=repository,
        id_generator=lambda: "dataset-1",
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )

    dataset = service.register_dataset(
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
    )
    activated = service.promote_dataset(dataset.dataset_id)

    reloaded_service = DatasetRegistryService(repository)
    reloaded = reloaded_service.get_dataset(dataset.dataset_id)

    assert activated.status == DatasetStatus.ACTIVE
    assert reloaded.status == DatasetStatus.ACTIVE
    assert reloaded.storage_uri == "s3://datasets/support-faq/2026-06-26.parquet"
