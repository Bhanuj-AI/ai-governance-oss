"""A separately-owned runtime adapter fixture used to prove the public Replay SPI.

This module deliberately lives outside ``src/ai_governance``. It consumes the
public Replay adapter registry and frozen controlled-intervention contract but
does not import Causal Audit orchestration or alter Replay core behavior.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from ai_governance.domain.replay import ReplayConfiguration
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.services import ReplayExecutionContext


class SchemaDrivenAgentRuntimeAdapter:
    """Minimal external adapter with deterministic, side-effect-free replay."""

    name = "external-schema-runtime/v1"

    def validate_configuration(
        self,
        source_execution: WorkflowExecution,
        configuration: ReplayConfiguration,
    ) -> None:
        capability = (source_execution.runtime_parameters or {}).get(
            "agent_runtime_replay", {}
        )
        if (
            not isinstance(capability, Mapping)
            or capability.get("adapter_id") != self.name
        ):
            raise ValueError(
                "Replay source does not declare the external runtime adapter."
            )

    def replay(
        self,
        source_execution: WorkflowExecution,
        configuration: ReplayConfiguration,
        context: ReplayExecutionContext,
    ) -> WorkflowExecution:
        if context.cancellation_token.is_cancelled:
            raise ValueError("Replay cancellation requested.")
        intervention = context.controlled_evidence_intervention
        if (
            intervention is None
            or not intervention.target_event_id
            or not intervention.policy_id
            or intervention.policy_version is None
            or not intervention.intervention_digest
            or not intervention.counterfactual_evidence_digest
        ):
            raise ValueError("External controlled replay requires governed provenance.")
        event = next(
            (
                item
                for item in source_execution.events
                if item.get("event_id") == intervention.target_event_id
            ),
            None,
        )
        if not isinstance(event, Mapping) or not isinstance(
            event.get("runtime_tool_call_id"), str
        ):
            raise TypeError("External replay target lacks a runtime tool-call ID.")
        score = 0.2
        return WorkflowExecution(
            workflow_id=source_execution.workflow_id,
            execution_id=context.new_execution_id,
            workflow_name=source_execution.workflow_name,
            workflow_version=source_execution.workflow_version,
            execution_status="COMPLETED",
            input={},
            final_state={"causal_audit_outcome_score": float(score)},
            events=[{"type": "EXTERNAL_CONTROLLED_REPLAY_COMPLETED"}],
            organization_id=context.organization_id,
            project_id=context.project_id,
            execution_adapter=self.name,
            artifact_refs=[intervention.source_evidence_reference],
            runtime_parameters={"isolated": True},
            metadata={
                "external_runtime": "schema-driven-fixture",
                "intervention_digest": intervention.intervention_digest,
            },
            created_at=datetime.now(UTC),
        )
