from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.domain.workflow_execution import WorkflowExecution
from kavach.repositories.sqlite.sqlite_evaluation_repository import (
    SQLiteEvaluationRepository,
)
from kavach.services.dataset_builder import (
    EvaluationDatasetBuilder,
)
from kavach.evaluation import EvaluationService
from kavach.workers.evaluation_worker import (
    EvaluationWorker,
)
from kavach.repositories.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)
from tests.providers.FakeProvider import FakeEvaluationProvider


def test_evaluation_worker() -> None:

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

    database = SQLiteDatabase("kavach.sqlite")
    database.initialize()

    evaluation_repository = SQLiteEvaluationRepository(database)

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
