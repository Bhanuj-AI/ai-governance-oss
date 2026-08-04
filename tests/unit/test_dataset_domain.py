from datetime import UTC, datetime

import pytest

from kavach.domain.datasets import (
    Dataset,
    DatasetDiff,
    DatasetStatus,
)


def test_dataset_requires_non_negative_record_count() -> None:
    with pytest.raises(ValueError):
        Dataset(
            dataset_id="dataset-1",
            name="support-faq",
            version="2026-06-26",
            description="Evaluation baseline",
            storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
            storage_type="S3",
            schema_version="v1",
            record_count=-1,
            checksum="sha256:abc123",
            creator="dataset-owner",
            created_at=datetime(2026, 6, 26, tzinfo=UTC),
            status=DatasetStatus.DRAFT,
        )


def test_dataset_diff_reports_metadata_and_change_presence() -> None:
    diff = DatasetDiff(
        baseline_dataset_id="dataset-1",
        candidate_dataset_id="dataset-2",
        name_changed=False,
        version_changed=True,
        description_changed=True,
        storage_location_changed=False,
        storage_type_changed=False,
        schema_version_changed=False,
        record_count_changed=True,
        checksum_changed=True,
    )

    assert diff.metadata_changed is True
    assert diff.has_changes is True
