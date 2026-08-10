from abc import ABC
from abc import abstractmethod

from ai_governance.domain.workflow_execution import WorkflowExecution


class ExecutionRepository(ABC):
    @abstractmethod
    def get_pending_executions(self) -> list[WorkflowExecution]:
        pass
