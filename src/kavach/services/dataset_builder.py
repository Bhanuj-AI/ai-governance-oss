from kavach.domain.evaluation_dataset import EvaluationDataset
from kavach.domain.workflow_execution import WorkflowExecution


class EvaluationDatasetBuilder:
    def build(self, execution: WorkflowExecution) -> EvaluationDataset:

        return EvaluationDataset(
            execution_id=execution.execution_id,
            input_text="",
            context_text="",
            output_text="",
            metadata={},
        )
