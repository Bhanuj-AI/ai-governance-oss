from kavach.repositories.in_memory_model_repository import (
    InMemoryModelRepository,
)
from kavach.repositories.model_repository import ModelRepository
from tests.repositories.contract.test_model_repository_contract import (
    ModelRepositoryContract,
)


class TestInMemoryModelRepository(ModelRepositoryContract):
    def repository(self) -> ModelRepository:
        return InMemoryModelRepository()
