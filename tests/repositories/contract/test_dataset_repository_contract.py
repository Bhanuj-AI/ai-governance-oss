from abc import ABC, abstractmethod
from datetime import UTC, datetime

from ai_governance.domain.datasets import (
    Dataset,
    DatasetStatus,
)
from ai_governance.repositories.dataset_repository import DatasetRepository


class DatasetRepositoryContract(ABC):
    """
    Behavioral contract every DatasetRepository implementation must satisfy.
    """

    @abstractmethod
    def repository(self) -> DatasetRepository:
        """
        Return a fresh dataset repository instance.
        """

    def create_dataset(self) -> Dataset:
        return Dataset(
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
            status=DatasetStatus.DRAFT,
        )

    def test_should_save_and_load_dataset(self) -> None:
        repository = self.repository()
        expected = self.create_dataset()

        repository.save(expected)

        assert repository.find_by_id(expected.dataset_id) == expected

    def test_should_find_versions_for_dataset_name(self) -> None:
        repository = self.repository()
        expected = self.create_dataset()

        repository.save(expected)

        assert repository.find_by_name(expected.name) == [expected]
        assert repository.find_by_name("missing") == []

    def test_should_find_dataset_by_name_and_version(self) -> None:
        repository = self.repository()
        expected = self.create_dataset()

        repository.save(expected)

        assert (
            repository.find_by_name_and_version(
                expected.name,
                expected.version,
            )
            == expected
        )
        assert (
            repository.find_by_name_and_version(
                expected.name,
                "missing",
            )
            is None
        )

    def test_should_replace_dataset_with_same_id(self) -> None:
        repository = self.repository()
        expected = self.create_dataset()
        replacement = Dataset(
            dataset_id=expected.dataset_id,
            name=expected.name,
            version=expected.version,
            description=expected.description,
            storage_uri=expected.storage_uri,
            storage_type=expected.storage_type,
            schema_version=expected.schema_version,
            record_count=expected.record_count,
            checksum=expected.checksum,
            creator=expected.creator,
            created_at=expected.created_at,
            status=DatasetStatus.ACTIVE,
        )

        repository.save(expected)
        repository.save(replacement)

        assert repository.find_by_id(expected.dataset_id) == replacement

    def test_should_find_all_datasets(self) -> None:
        repository = self.repository()
        expected = self.create_dataset()

        repository.save(expected)

        assert repository.find_all() == [expected]
