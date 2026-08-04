from kavach.repositories.dataset_repository import DatasetRepository
from kavach.repositories.in_memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from tests.repositories.contract.test_dataset_repository_contract import (
    DatasetRepositoryContract,
)


class TestInMemoryDatasetRepository(DatasetRepositoryContract):
    def repository(self) -> DatasetRepository:
        return InMemoryDatasetRepository()
