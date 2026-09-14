"""Pydantic models for the Agent Execution Trace API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

# -- Request models -----------------------------------------------------------


class AgentExecutionStartRequest(BaseModel):
    """Ingest an EXECUTION_STARTED event from an external runtime."""

    agent_id: str = Field(min_length=1, max_length=256)
    agent_name: str = Field(min_length=1, max_length=256)
    agent_version: str = Field(min_length=1, max_length=64)
    external_execution_id: str = Field(min_length=1, max_length=512)
    runtime_provider: str = Field(min_length=1, max_length=128)
    correlation_id: str | None = Field(None, max_length=256)
    parent_execution_id: str | None = Field(None, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentExecutionEventRequest(BaseModel):
    """Ingest a runtime event, including optional typed workflow-step evidence."""

    event_type: str = Field(..., description="Event type from the vocabulary.")
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Operational metadata. Raw prompts, responses, credentials, and reasoning traces are prohibited.",
    )
    idempotency_key: str | None = Field(
        None, max_length=256, description="Optional idempotency key for duplicate-safe delivery."
    )
    correlation_id: str | None = Field(None, max_length=256)
    causation_id: str | None = Field(None, max_length=256)
    actor_id: str | None = Field(None, max_length=256)
    actor_type: str | None = Field(None, description="Agent, Model, Tool, Governance, Evaluator, or System.")
    step_id: str | None = Field(
        None,
        min_length=1,
        max_length=256,
        description="Stable workflow-step correlation ID. Required for WORKFLOW_STEP.",
    )
    step_name: str | None = Field(
        None,
        min_length=1,
        max_length=256,
        description="Human-readable workflow-step name. Required for WORKFLOW_STEP.",
    )
    lifecycle: str | None = Field(
        None,
        min_length=1,
        max_length=32,
        description="Workflow-step lifecycle: STARTED, COMPLETED, or FAILED.",
    )
    parent_step_id: str | None = Field(
        None,
        min_length=1,
        max_length=256,
        description="Optional parent workflow-step ID in this execution.",
    )
    source_kind: str | None = Field(
        None,
        min_length=1,
        max_length=256,
        description="Optional namespaced source concept, for example langgraph.node.",
    )
    resource_references: list[str] = Field(
        default_factory=list, description="References to governed resources touched by this event."
    )
    evidence_references: list[str] = Field(
        default_factory=list, description="References to evidence/artifacts stored elsewhere."
    )
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def validate_workflow_step_fields(self) -> AgentExecutionEventRequest:
        workflow_fields = (
            self.step_id,
            self.step_name,
            self.lifecycle,
            self.parent_step_id,
            self.source_kind,
        )
        if self.event_type == "WORKFLOW_STEP":
            missing = [
                name
                for name, value in (
                    ("step_id", self.step_id),
                    ("step_name", self.step_name),
                    ("lifecycle", self.lifecycle),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    "WORKFLOW_STEP events require " + ", ".join(missing) + "."
                )
            if self.parent_step_id == self.step_id:
                raise ValueError("parent_step_id must not equal step_id.")
        elif any(value is not None for value in workflow_fields):
            raise ValueError(
                "step fields are valid only when event_type is WORKFLOW_STEP."
            )
        return self


class AgentExecutionCompleteRequest(BaseModel):
    """Mark an execution as terminal."""

    status: str = Field(..., description="SUCCEEDED, FAILED, or CANCELLED.")


# -- Response models ------------------------------------------------------------


class AgentExecutionResponse(BaseModel):
    """Full agent execution record."""

    execution_id: str
    agent_id: str
    agent_name: str
    agent_version: str
    external_execution_id: str
    runtime_provider: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    correlation_id: str | None = None
    parent_execution_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = 0
    created_at: datetime
    updated_at: datetime


class AgentExecutionSummaryResponse(BaseModel):
    """Lightweight execution listing item."""

    execution_id: str
    agent_id: str
    agent_name: str
    runtime_provider: str
    external_execution_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    event_count: int

    @property
    def duration_seconds(self) -> float | None:
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()


class AgentExecutionListResponse(BaseModel):
    """Paginated execution listing."""

    items: list[AgentExecutionSummaryResponse]
    next_cursor: str | None = None


class AgentExecutionAgentSummaryResponse(BaseModel):
    """Aggregated execution evidence for one observed agent."""

    agent_id: str
    agent_name: str
    runtime_provider: str
    execution_count: int
    succeeded_count: int
    failed_count: int
    running_count: int
    last_started_at: datetime


class AgentExecutionAgentListResponse(BaseModel):
    """Offset-paginated observed-agent index."""

    items: list[AgentExecutionAgentSummaryResponse]
    next_offset: int | None = None


class AgentExecutionEventResponse(BaseModel):
    """One event in the execution timeline."""

    event_id: str
    execution_id: str
    event_type: str
    sequence_number: int
    occurred_at: datetime
    received_at: datetime
    late_for_runtime_findings: bool = False
    runtime_findings_finalization_cutoff_at: datetime | None = None
    runtime_findings_lateness_policy_hours: int | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    actor_id: str | None = None
    actor_type: str | None = None
    step_id: str | None = None
    step_name: str | None = None
    lifecycle: str | None = None
    parent_step_id: str | None = None
    source_kind: str | None = None
    resource_references: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    event_schema_version: str = "1"


class AgentExecutionDetailResponse(BaseModel):
    """Full execution detail with event timeline."""

    execution: AgentExecutionResponse
    events: list[AgentExecutionEventResponse]
    event_counts: dict[str, int] = Field(default_factory=dict)


class AgentExecutionStartedResponse(BaseModel):
    """Response after successful execution start ingestion."""

    execution: AgentExecutionResponse


class AgentExecutionEventIngestedResponse(BaseModel):
    """Response after successful event ingestion."""

    event: AgentExecutionEventResponse


class AgentExecutionCompletedResponse(BaseModel):
    """Response after marking an execution terminal."""

    execution: AgentExecutionResponse


class AgentExecutionPageResponse(BaseModel):
    """Cursor-based paginated response for execution listings."""

    items: list[AgentExecutionSummaryResponse]
    next_cursor: str | None = None
