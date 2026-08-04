from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class WorkflowExecution:
    """
    Canonical representation of a workflow execution.

    This model represents a fully reconstructed workflow execution and
    serves as the contract between the Replay Plane and the Evaluation Plane.

    WorkflowExecution abstracts away the underlying storage, audit events,
    workflow framework, and runtime implementation details, allowing the
    evaluation framework to operate on a consistent execution model.

    Typical flow:

        AGENT_EXECUTION_AUDIT
                ↓
        Replay Framework
                ↓
        WorkflowExecution
                ↓
        Evaluation Framework

    The Evaluation Plane should never directly interact with audit tables,
    workflow state storage, or replay infrastructure. Instead, it consumes
    WorkflowExecution instances produced by the Replay Plane.

    Design Goals:

    - Provider agnostic
    - Runtime agnostic
    - Storage agnostic
    - Replay friendly
    - Evaluation friendly
    """

    workflow_id: str
    """
    Unique workflow identifier.
    """

    execution_id: str
    """
    Unique workflow execution identifier.
    """

    workflow_name: str
    """
    Human-readable workflow name.

    Example:
        claim-validation
        investigation-workflow
    """

    workflow_version: str
    """
    Version of the workflow definition that produced this execution.
    """

    execution_status: str
    """
    Final execution status.

    Example:
        COMPLETED
        FAILED
        CANCELLED
    """

    input: dict[str, Any]
    """
    Original workflow input.
    """

    final_state: dict[str, Any]
    """
    Final workflow state after execution completion.
    """

    events: list[dict[str, Any]]
    """
    Ordered workflow execution events captured during runtime.

    Example:
        WORKFLOW_STARTED
        NODE_STARTED
        NODE_COMPLETED
        WORKFLOW_COMPLETED

    These events enable replay, trace reconstruction, and governance
    analysis.
    """

    organization_id: str = "org_default"
    project_id: str = "project_default"
    execution_adapter: str = "historical"
    input_snapshot_ref: str | None = None
    state_snapshot_ref: str | None = None
    artifact_refs: list[str] | None = None
    prompt_refs: list[str] | None = None
    model_refs: list[str] | None = None
    dataset_refs: list[str] | None = None
    policy_refs: list[str] | None = None
    runtime_parameters: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
