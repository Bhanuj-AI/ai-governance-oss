from datetime import UTC, datetime

from kavach.domain.datasets import (
    Dataset,
    DatasetStatus,
)
from kavach.repositories.mappers.dataset_persistence_mapper import (
    DatasetPersistenceMapper,
)


def test_dataset_persistence_mapper_round_trips_dataset() -> None:
    dataset = Dataset(
        dataset_id="dataset-1",
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
        status=DatasetStatus.ACTIVE,
    )

    record = DatasetPersistenceMapper.to_persistence_record(dataset)
    reloaded = DatasetPersistenceMapper.from_persistence_record(record)

    assert reloaded == dataset
