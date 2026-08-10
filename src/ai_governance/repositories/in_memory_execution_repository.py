from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.repositories.execution_repository import ExecutionRepository


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
