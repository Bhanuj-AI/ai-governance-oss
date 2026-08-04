from kavach.domain.evaluation_result import EvaluationResult
from kavach.domain.workflow_execution import WorkflowExecution
from kavach.repositories.execution_repository import ExecutionRepository


class InMemoryExecutionRepository(ExecutionRepository):
    def __init__(self, executions: list[WorkflowExecution]):
        self._executions = executions

    def get_pending_executions(self) -> list[WorkflowExecution]:

        return self._executions

    @property
    def results(
        self,
    ) -> list[EvaluationResult]:
        return self._results
