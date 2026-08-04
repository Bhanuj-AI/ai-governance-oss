from kavach.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from kavach.repositories.in_memory_evaluation_run_repository import (
    InMemoryEvaluationRunRepository,
)
from tests.repositories.contract.test_evaluation_run_repository_contract import (
    EvaluationRunRepositoryContract,
)


class TestInMemoryEvaluationRunRepository(
    EvaluationRunRepositoryContract
):
    def repository(self) -> EvaluationRunRepository:
        return InMemoryEvaluationRunRepository()
