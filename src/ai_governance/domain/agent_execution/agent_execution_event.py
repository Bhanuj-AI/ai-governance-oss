"""AgentExecutionEvent — append-only immutable runtime activity records.

Events are never updated after persistence. Each event carries an explicit
schema version; ingestion rejects unsupported future versions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any


class EventType(str, Enum):
    """Phase 1 event vocabulary."""

    EXECUTION_STARTED = "EXECUTION_STARTED"
    MODEL_CALL = "MODEL_CALL"
    TOOL_CALL = "TOOL_CALL"
    WORKFLOW_STEP = "WORKFLOW_STEP"
    GOVERNANCE_DECISION = "GOVERNANCE_DECISION"
    EVALUATION = "EVALUATION"
    ERROR = "ERROR"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"


class ActorType(str, Enum):
    """Who or what triggered this event."""

    AGENT = "AGENT"
    MODEL = "MODEL"
    TOOL = "TOOL"
    GOVERNANCE = "GOVERNANCE"
    EVALUATOR = "EVALUATOR"
    SYSTEM = "SYSTEM"


class WorkflowStepLifecycle(str, Enum):
    """Lifecycle of one logical unit of orchestrated execution."""

    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


_SOURCE_KIND_PATTERN = re.compile(
    r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$"
)
_WORKFLOW_STEP_FIELD_MAX_LENGTH = 256
_TOOL_CALL_CONTEXT_FIELD_MAX_LENGTH = 256
_TOOL_CALL_CONTEXT_MAX_DEPENDENCIES = 64
_SUPPORTED_TOOL_CALL_CONTEXT_SCHEMA_VERSIONS = frozenset({"1"})


@dataclass(frozen=True)
class WorkflowStep:
    """Provider-neutral structure carried by a ``WORKFLOW_STEP`` event.

    A workflow step represents an orchestration unit.  It does not imply a
    model call, a tool invocation, or deterministic execution.  Framework
    adapters may use ``source_kind`` to preserve the originating concept
    without changing the canonical event semantics.
    """

    step_id: str
    step_name: str
    lifecycle: WorkflowStepLifecycle
    parent_step_id: str | None = None
    source_kind: str | None = None

    def __post_init__(self) -> None:
        for name, value in (("step_id", self.step_id), ("step_name", self.step_name)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty.")
            if len(value) > _WORKFLOW_STEP_FIELD_MAX_LENGTH:
                raise ValueError(
                    f"{name} must not exceed {_WORKFLOW_STEP_FIELD_MAX_LENGTH} characters."
                )
        if self.parent_step_id is not None:
            if not isinstance(self.parent_step_id, str) or not self.parent_step_id.strip():
                raise ValueError("parent_step_id must not be blank.")
            if len(self.parent_step_id) > _WORKFLOW_STEP_FIELD_MAX_LENGTH:
                raise ValueError(
                    "parent_step_id must not exceed "
                    f"{_WORKFLOW_STEP_FIELD_MAX_LENGTH} characters."
                )
            if self.parent_step_id == self.step_id:
                raise ValueError("parent_step_id must not equal step_id.")
        if self.source_kind is not None and (
            not isinstance(self.source_kind, str)
            or len(self.source_kind) > _WORKFLOW_STEP_FIELD_MAX_LENGTH
            or not _SOURCE_KIND_PATTERN.fullmatch(self.source_kind)
        ):
            raise ValueError(
                "source_kind must be a bounded lowercase namespaced identifier, "
                "for example 'langgraph.node'."
            )
        try:
            lifecycle = WorkflowStepLifecycle(self.lifecycle)
        except ValueError as exc:
            raise ValueError(
                "lifecycle must be STARTED, COMPLETED, or FAILED."
            ) from exc
        object.__setattr__(self, "lifecycle", lifecycle)


@dataclass(frozen=True)
class ToolCallContext:
    """Provider-neutral execution structure observed for a tool invocation."""

    schema_version: str
    runtime_tool_call_id: str
    tool_call_group_id: str
    depends_on_tool_call_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version not in _SUPPORTED_TOOL_CALL_CONTEXT_SCHEMA_VERSIONS:
            raise ValueError(
                "Unsupported tool-call context schema version "
                f"'{self.schema_version}'; supported versions: "
                f"{sorted(_SUPPORTED_TOOL_CALL_CONTEXT_SCHEMA_VERSIONS)}."
            )
        for name, value in (
            ("runtime_tool_call_id", self.runtime_tool_call_id),
            ("tool_call_group_id", self.tool_call_group_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be blank.")
            if len(value) > _TOOL_CALL_CONTEXT_FIELD_MAX_LENGTH:
                raise ValueError(
                    f"{name} must not exceed "
                    f"{_TOOL_CALL_CONTEXT_FIELD_MAX_LENGTH} characters."
                )

        dependencies = tuple(self.depends_on_tool_call_ids)
        if len(dependencies) > _TOOL_CALL_CONTEXT_MAX_DEPENDENCIES:
            raise ValueError(
                "depends_on_tool_call_ids must not contain more than "
                f"{_TOOL_CALL_CONTEXT_MAX_DEPENDENCIES} items."
            )
        if len(set(dependencies)) != len(dependencies):
            raise ValueError("depends_on_tool_call_ids must be unique.")
        for dependency_id in dependencies:
            if not isinstance(dependency_id, str) or not dependency_id.strip():
                raise ValueError(
                    "depends_on_tool_call_ids must not contain blank values."
                )
            if len(dependency_id) > _TOOL_CALL_CONTEXT_FIELD_MAX_LENGTH:
                raise ValueError(
                    "depends_on_tool_call_ids values must not exceed "
                    f"{_TOOL_CALL_CONTEXT_FIELD_MAX_LENGTH} characters."
                )
            if dependency_id == self.runtime_tool_call_id:
                raise ValueError("runtime_tool_call_id must not depend on itself.")
        object.__setattr__(self, "depends_on_tool_call_ids", dependencies)


# Fields that must never be persisted in event attributes.
_PROHIBITED_KEYS = frozenset(
    {
        "prompt",
        "system_prompt",
        "response",
        "messages",
        "conversation",
        "chain_of_thought",
        "chain_of_thoughts",
        "reasoning",
        "credentials",
        "authorization",
        "authorization_header",
        "authorization_headers",
        "api_key",
        "apikey",
        "token",
        "password",
        "secret",
        "tool_payload",
        "tool_output",
        "tool_arguments",
        "tool_result",
        # Reject the removed descriptor-metadata identity path so a second
        # runtime tool-call identity cannot reappear in attributes.
        "external_tool_call_id",
    }
)

# Schema versions supported .
_SUPPORTED_SCHEMA_VERSIONS = frozenset({"1"})

def _find_prohibited_key_in_value(value: Any, path: str = "") -> str | None:
    """Recursively search for prohibited keys nested inside dicts/lists.

    Returns the first prohibited key found (with its dotted path), or None.
    """
    if isinstance(value, dict):
        for k, v in value.items():
            normalized = str(k).lower().replace("-", "_").replace(" ", "_")
            current_path = f"{path}.{k}" if path else str(k)
            if normalized in _PROHIBITED_KEYS:
                return current_path
            result = _find_prohibited_key_in_value(v, current_path)
            if result is not None:
                return result
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            result = _find_prohibited_key_in_value(item, f"{path}[{i}]")
            if result is not None:
                return result
    return None




@dataclass(frozen=True)
class AgentExecutionEvent:
    """An immutable, append-only record of one agent runtime activity.

    Attributes:
        event_id: Unique event identifier (runtime or platform generated).
        execution_id: Parent agent execution reference.
        tenant_id: Deprecated alias for organization_id; use that instead.
        organization_id: Tenant organization scope.
        project_id: Tenant project scope (may be None).
        event_type: Semantic category of this event.
        sequence_number: Monotonically increasing position within the execution.
        occurred_at: When the activity happened in the external runtime.
        received_at: When AI Governance Platform ingested this event.
        correlation_id: Optional cross-cutting correlation identifier.
        causation_id: ID of the event that caused this one (may be None).
        actor_id: Identifier for the actor (agent, model, tool, etc.).
        actor_type: Semantic type of the actor.
        resource_references: References to governed resources touched by this event.
        evidence_references: References to evidence/artifacts stored elsewhere.
        attributes: Operational metadata; raw payloads are prohibited.
        event_schema_version: Schema version string (Phase 1 = "1").
    """

    event_id: str
    execution_id: str
    organization_id: str
    project_id: str | None
    event_type: EventType
    sequence_number: int
    occurred_at: datetime
    received_at: datetime
    correlation_id: str | None
    causation_id: str | None
    actor_id: str | None
    actor_type: ActorType | None
    workflow_step: WorkflowStep | None = None
    tool_call_context: ToolCallContext | None = None
    late_for_runtime_findings: bool = False
    runtime_findings_finalization_cutoff_at: datetime | None = None
    runtime_findings_lateness_policy_hours: int | None = None
    resource_references: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)
    event_schema_version: str = "1"

    def __post_init__(self) -> None:
        for name, value in (
            ("event_id", self.event_id),
            ("execution_id", self.execution_id),
            ("organization_id", self.organization_id),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty.")
        if self.project_id is not None and not self.project_id.strip():
            raise ValueError("project_id must not be blank.")
        if self.sequence_number < 0:
            raise ValueError("sequence_number must be non-negative.")
        if self.event_schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported event schema version '{self.event_schema_version}'; "
                f"Phase 1 supports: {sorted(_SUPPORTED_SCHEMA_VERSIONS)}."
            )
        if self.received_at < self.occurred_at:
            raise ValueError("received_at must not precede occurred_at.")
        if self.event_type is EventType.WORKFLOW_STEP:
            if not isinstance(self.workflow_step, WorkflowStep):
                raise ValueError(
                    "WORKFLOW_STEP events require typed workflow_step evidence."
                )
        elif self.workflow_step is not None:
            raise ValueError(
                "workflow_step evidence is valid only for WORKFLOW_STEP events."
            )
        if self.event_type is EventType.TOOL_CALL:
            if self.tool_call_context is not None and not isinstance(
                self.tool_call_context, ToolCallContext
            ):
                raise TypeError("tool_call_context must be a ToolCallContext.")
        elif self.tool_call_context is not None:
            raise ValueError("tool_call_context is valid only for TOOL_CALL events.")
        # Validate resource/evidence references are non-empty strings.
        for ref in self.resource_references:
            if not str(ref).strip():
                raise ValueError("resource_references must not contain empty strings.")
        for ref in self.evidence_references:
            if not str(ref).strip():
                raise ValueError("evidence_references must not contain empty strings.")
        # Sanitize attributes: reject prohibited raw payload keys at any depth.
        attrs = dict(self.attributes)
        for key, value in attrs.items():
            normalized = str(key).lower().replace("-", "_").replace(" ", "_")
            if normalized in _PROHIBITED_KEYS:
                raise ValueError(
                    f"Event attributes must not contain prohibited key '{key}'; "
                    "raw prompts, responses, credentials, and reasoning traces "
                    "are not persisted."
                )
            # Recursively check nested dicts/lists for prohibited keys.
            nested = _find_prohibited_key_in_value(value)
            if nested is not None:
                raise ValueError(
                    f"Event attributes must not contain prohibited key '{nested}'; "
                    "raw prompts, responses, credentials, and reasoning traces "
                    "are not persisted."
                )
        object.__setattr__(self, "attributes", MappingProxyType(attrs))

    # -- Read helpers ---------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        return self.event_type in (
            EventType.EXECUTION_STARTED,
            EventType.EXECUTION_COMPLETED,
        )

    @property
    def is_error(self) -> bool:
        return self.event_type is EventType.ERROR

    def with_sequence(self, sequence_number: int) -> AgentExecutionEvent:
        """Return a copy with an updated sequence number."""
        return replace(self, sequence_number=sequence_number)
