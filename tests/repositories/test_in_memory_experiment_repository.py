from kavach.repositories.experiment_repository import ExperimentRepository
from kavach.repositories.in_memory_experiment_repository import (
    InMemoryExperimentRepository,
)
from tests.repositories.contract.test_experiment_repository_contract import (
    ExperimentRepositoryContract,
)


class TestInMemoryExperimentRepository(ExperimentRepositoryContract):
    def repository(self) -> ExperimentRepository:
        return InMemoryExperimentRepository()
