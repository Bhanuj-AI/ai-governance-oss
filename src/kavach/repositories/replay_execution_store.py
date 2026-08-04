"""Shared payload mapping for durable Replay workflow-execution stores."""

from __future__ import annotations

from datetime import datetime

from kavach.domain.workflow_execution import WorkflowExecution


def workflow_execution_payload(execution: WorkflowExecution) -> dict[str, object]:
    """Return the complete immutable execution evidence stored by Replay."""
    return {
        "workflow_id": execution.workflow_id,
        "execution_id": execution.execution_id,
        "workflow_name": execution.workflow_name,
        "workflow_version": execution.workflow_version,
        "execution_status": execution.execution_status,
        "input": execution.input,
        "final_state": execution.final_state,
        "events": execution.events,
        "organization_id": execution.organization_id,
        "project_id": execution.project_id,
        "execution_adapter": execution.execution_adapter,
        "input_snapshot_ref": execution.input_snapshot_ref,
        "state_snapshot_ref": execution.state_snapshot_ref,
        "artifact_refs": execution.artifact_refs,
        "prompt_refs": execution.prompt_refs,
        "model_refs": execution.model_refs,
        "dataset_refs": execution.dataset_refs,
        "policy_refs": execution.policy_refs,
        "runtime_parameters": execution.runtime_parameters,
        "metadata": execution.metadata,
        "created_at": execution.created_at.isoformat() if execution.created_at else None,
    }


def workflow_execution_from_payload(payload: dict[str, object]) -> WorkflowExecution:
    """Reconstruct a WorkflowExecution without resolving mutable live state."""
    created_at = payload.get("created_at")
    return WorkflowExecution(
        workflow_id=str(payload["workflow_id"]),
        execution_id=str(payload["execution_id"]),
        workflow_name=str(payload["workflow_name"]),
        workflow_version=str(payload["workflow_version"]),
        execution_status=str(payload["execution_status"]),
        input=dict(payload["input"]),
        final_state=dict(payload["final_state"]),
        events=list(payload["events"]),
        organization_id=str(payload["organization_id"]),
        project_id=str(payload["project_id"]),
        execution_adapter=str(payload.get("execution_adapter") or "historical"),
        input_snapshot_ref=payload.get("input_snapshot_ref") or None,
        state_snapshot_ref=payload.get("state_snapshot_ref") or None,
        artifact_refs=payload.get("artifact_refs") or None,
        prompt_refs=payload.get("prompt_refs") or None,
        model_refs=payload.get("model_refs") or None,
        dataset_refs=payload.get("dataset_refs") or None,
        policy_refs=payload.get("policy_refs") or None,
        runtime_parameters=payload.get("runtime_parameters") or None,
        metadata=dict(payload.get("metadata") or {}),
        created_at=datetime.fromisoformat(str(created_at)) if created_at else None,
    )
