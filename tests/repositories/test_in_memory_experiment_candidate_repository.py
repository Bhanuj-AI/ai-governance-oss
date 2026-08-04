from kavach.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from kavach.repositories.in_memory_experiment_candidate_repository import (
    InMemoryExperimentCandidateRepository,
)
from tests.repositories.contract.test_experiment_candidate_repository_contract import (
    ExperimentCandidateRepositoryContract,
)


class TestInMemoryExperimentCandidateRepository(
    ExperimentCandidateRepositoryContract
):
    def repository(self) -> ExperimentCandidateRepository:
        return InMemoryExperimentCandidateRepository()
