from pathlib import Path

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation import EvaluationService
from ai_governance.repositories.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)
from ai_governance.repositories.sqlite.sqlite_evaluation_repository import (
    SQLiteEvaluationRepository,
)
from ai_governance.services.dataset_builder import EvaluationDatasetBuilder
from ai_governance.services.history import EvaluationHistoryService
from ai_governance.workers.evaluation_worker import EvaluationWorker
from tests.providers.FakeProvider import FakeEvaluationProvider


def test_sqlite_evaluation_history_service_returns_worker_results(
    tmp_path: Path,
) -> None:
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
    execution_repository = InMemoryExecutionRepository(
        [
            execution,
        ]
    )
    database = SQLiteDatabase(tmp_path / "ai_governance.db")
    database.initialize()
    evaluation_repository = SQLiteEvaluationRepository(database)

    worker = EvaluationWorker(
        evaluation_service=EvaluationService(
            provider=FakeEvaluationProvider(),
            dataset_builder=EvaluationDatasetBuilder(),
        ),
        execution_repository=execution_repository,
        evaluation_repository=evaluation_repository,
    )
    history_service = EvaluationHistoryService(evaluation_repository)

    worker.run()
    history = history_service.get_execution_history("exec-1")

    assert history.execution_id == "exec-1"
    assert history.evaluation_count == 1
    assert history.records[0].evaluation_id == "1"
    assert history.records[0].evaluator_type == "fake"
    assert history.records[0].metrics[0].metric_name == "answer_relevance"
    assert history.records[0].metrics[0].metric_value == 1.0
