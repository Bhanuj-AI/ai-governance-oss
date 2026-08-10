from dataclasses import dataclass
from typing import Any


@dataclass
class EvaluationDataset:
    """
    Canonical evaluation dataset consumed by evaluation providers.

    This model represents a provider-agnostic view of an agent execution
    and serves as the contract between the AI Governance Control Plane Evaluation Plane and
    evaluation frameworks such as TruLens, Phoenix, DeepEval, RAGAS,
    Snowflake Cortex Judge, and custom evaluators.

    The purpose of this model is to normalize workflow executions into a
    common evaluation format that can be understood by any evaluation
    provider without requiring knowledge of:

    - LangGraph
    - Workflow implementations
    - Audit events
    - Replay mechanics
    - Storage systems
    - Runtime infrastructure

    Typical flow:

        WorkflowExecution
                ↓
        EvaluationDatasetBuilder
                ↓
        EvaluationDataset
                ↓
        EvaluationProvider
                ↓
        EvaluationResult

    Field Mapping

    AI Governance Control Plane                    TruLens

    input_text      →         prompt / question
    context_text    →         context / source
    output_text     →         response / statement

    This mapping allows AI Governance Control Plane to remain provider-independent while
    supporting multiple evaluation frameworks.
    """

    execution_id: str
    """
    Unique workflow execution identifier.

    Used to correlate evaluation results with the originating
    workflow execution.
    """

    input_text: str
    """
    Original user request or workflow input.

    Examples:

    - Customer claim description
    - User question
    - Agent task request
    - Investigation objective

    Used by metrics such as:

    - Answer Relevance
    - Question Relevance
    """

    context_text: str
    """
    Supporting context used by the agent to generate its response.

    Examples:

    - Retrieved RAG documents
    - Evidence processing results
    - OCR outputs
    - Knowledge base content
    - Policy documentation

    Used by metrics such as:

    - Context Relevance
    - Groundedness
    - Faithfulness
    """

    output_text: str
    """
    Final agent response produced during workflow execution.

    Examples:

    - Claim decision
    - Investigation summary
    - Generated answer
    - Recommendation

    Used by metrics such as:

    - Answer Relevance
    - Groundedness
    - Correctness
    """

    metadata: dict[str, Any]
    """
    Optional evaluation metadata.

    Metadata is not directly evaluated but provides additional
    context for governance, analytics, filtering, and reporting.

    Example:

    {
        "workflow_name": "claim-validation",
        "workflow_version": "1.0.0",
        "agent_version": "2.1.0",
        "prompt_version": "3.0.0",
        "model_name": "gpt-4o"
    }

    Future governance capabilities such as replay analysis,
    decision drift detection, and evaluation trend reporting
    may consume this metadata.
    """
