"""AgentExecutionEvent — append-only immutable runtime activity records.

Events are never updated after persistence. Each event carries an explicit
schema version; ingestion rejects unsupported future versions.
"""

from __future__ import annotations

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
