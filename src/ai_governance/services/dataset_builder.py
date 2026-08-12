from ai_governance.domain.evaluation_dataset import EvaluationDataset
from ai_governance.domain.workflow_execution import WorkflowExecution


class EvaluationDatasetBuilder:
    def build(self, execution: WorkflowExecution) -> EvaluationDataset:
        """Build evaluator input from the exact execution evidence.

        Evaluation providers must not recreate candidate configuration or
        infer an answer from metadata.  A completed execution is therefore the
        sole source for input, retrieval context, and model output.
        """
        input_text = str(
            execution.input.get("input")
            or execution.input.get("question")
            or execution.input.get("query")
            or ""
        )
        output_text = str(execution.final_state.get("answer") or "")
        return EvaluationDataset(
            execution_id=execution.execution_id,
            input_text=input_text,
            context_text=str(execution.final_state.get("context") or ""),
            output_text=output_text,
            metadata=dict(execution.metadata),
        )
