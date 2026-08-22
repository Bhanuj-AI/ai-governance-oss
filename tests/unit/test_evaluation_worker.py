from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation import EvaluationService
from ai_governance.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from ai_governance.repositories.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)
from ai_governance.services.dataset_builder import (
    EvaluationDatasetBuilder,
)
from ai_governance.workers.evaluation_worker import (
    EvaluationWorker,
)
from tests.providers.FakeProvider import FakeEvaluationProvider


def test_evaluation_worker():

    execution = WorkflowExecution(
        workflow_id="wf-1",
        execution_id="exec-1",
        workflow_name="claim-validation",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={},
        final_state={},
        events=[],
    )

    execution_repository = InMemoryExecutionRepository([execution])

    evaluation_repository = InMemoryEvaluationRepository()

    evaluation_service = EvaluationService(
        provider=FakeEvaluationProvider(),
        dataset_builder=EvaluationDatasetBuilder(),
    )

    worker = EvaluationWorker(
        evaluation_service=evaluation_service,
        execution_repository=execution_repository,
        evaluation_repository=evaluation_repository,
    )

    worker.run()

    results = evaluation_repository.find_by_execution_id("exec-1")

    assert len(results) == 1
