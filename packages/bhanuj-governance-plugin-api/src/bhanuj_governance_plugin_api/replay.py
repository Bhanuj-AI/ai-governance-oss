"""Provider-neutral, governed replay contracts for external runtime plugins."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Protocol

REPLAY_INTERVENTION_ENVELOPE_SCHEMA_VERSION = "replay-intervention-envelope/v1"
_STRATEGIES = frozenset({"NULLIFY", "REPLACE", "PERTURB"})


class ReplayCancellationToken(Protocol):
    """Cooperative cancellation visible to an adapter at safe boundaries."""

    @property
    def is_cancelled(self) -> bool: ...


@dataclass(frozen=True)
class ReplayInterventionEnvelope:
    """The fixed, reference-only policy authorization for a controlled replay."""

    policy_id: str
    policy_version: int
    external_execution_id: str
    runtime_tool_call_id: str
    intervention_provider: str
    intervention_provider_version: str
    strategy: str
    original_evidence_digest: str
    counterfactual_reference: str
    counterfactual_digest: str
    intervention_digest: str
    schema_version: str = REPLAY_INTERVENTION_ENVELOPE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name, value in (
            ("policy_id", self.policy_id),
            ("external_execution_id", self.external_execution_id),
            ("runtime_tool_call_id", self.runtime_tool_call_id),
            ("intervention_provider", self.intervention_provider),
            ("intervention_provider_version", self.intervention_provider_version),
            ("original_evidence_digest", self.original_evidence_digest),
            ("counterfactual_reference", self.counterfactual_reference),
            ("counterfactual_digest", self.counterfactual_digest),
            ("intervention_digest", self.intervention_digest),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Replay intervention envelope {name} is required.")
        if (
            not isinstance(self.policy_version, int)
            or isinstance(self.policy_version, bool)
            or self.policy_version < 1
        ):
            raise ValueError(
                "Replay intervention envelope policy_version must be positive."
            )
        if self.strategy not in _STRATEGIES:
            raise ValueError("Replay intervention envelope strategy is unsupported.")
        if self.schema_version != REPLAY_INTERVENTION_ENVELOPE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported Replay intervention envelope schema version: {self.schema_version!r}."
            )

    def to_payload(self) -> dict[str, object]:
        """Serialise precisely the v1 reference-only wire shape."""
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "external_execution_id": self.external_execution_id,
            "runtime_tool_call_id": self.runtime_tool_call_id,
            "intervention_provider": self.intervention_provider,
            "intervention_provider_version": self.intervention_provider_version,
            "strategy": self.strategy,
            "original_evidence_digest": self.original_evidence_digest,
            "counterfactual_reference": self.counterfactual_reference,
            "counterfactual_digest": self.counterfactual_digest,
            "intervention_digest": self.intervention_digest,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayInterventionEnvelope:
        """Parse only a complete v1 envelope and reject unknown fields."""
        expected = set(cls.__dataclass_fields__)
        if set(payload) != expected:
            raise ValueError(
                "Replay intervention envelope payload has an unsupported shape."
            )
        return cls(
            policy_id=_required_string(payload, "policy_id"),
            policy_version=_required_version(payload),
            external_execution_id=_required_string(payload, "external_execution_id"),
            runtime_tool_call_id=_required_string(payload, "runtime_tool_call_id"),
            intervention_provider=_required_string(payload, "intervention_provider"),
            intervention_provider_version=_required_string(
                payload, "intervention_provider_version"
            ),
            strategy=_required_string(payload, "strategy"),
            original_evidence_digest=_required_string(
                payload, "original_evidence_digest"
            ),
            counterfactual_reference=_required_string(
                payload, "counterfactual_reference"
            ),
            counterfactual_digest=_required_string(payload, "counterfactual_digest"),
            intervention_digest=_required_string(payload, "intervention_digest"),
            schema_version=_required_string(payload, "schema_version"),
        )


@dataclass(frozen=True)
class ReplayExecutionContext:
    """Host-owned attempt metadata exposed to a runtime adapter."""

    replay_id: str
    source_execution_id: str
    new_execution_id: str
    organization_id: str
    project_id: str
    actor_id: str
    request_id: str
    correlation_id: str | None
    attempt: int
    cancellation_token: ReplayCancellationToken
    metadata: Mapping[str, Any]
    controlled_evidence_intervention: object | None = None
    intervention_envelope: ReplayInterventionEnvelope | None = None


@dataclass(frozen=True)
class ReplayExecutionResult:
    """Runtime-produced data that Core materialises as its workflow execution."""

    execution_status: str
    input: Mapping[str, Any] = field(default_factory=dict)
    final_state: Mapping[str, Any] = field(default_factory=dict)
    events: Sequence[Mapping[str, Any]] = ()
    artifact_refs: Sequence[str] = ()
    runtime_parameters: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.execution_status, str)
            or not self.execution_status.strip()
        ):
            raise ValueError("Replay execution result status is required.")
        object.__setattr__(self, "input", MappingProxyType(dict(self.input)))
        object.__setattr__(
            self, "final_state", MappingProxyType(dict(self.final_state))
        )
        object.__setattr__(
            self, "events", tuple(MappingProxyType(dict(item)) for item in self.events)
        )
        object.__setattr__(self, "artifact_refs", tuple(self.artifact_refs))
        object.__setattr__(
            self, "runtime_parameters", MappingProxyType(dict(self.runtime_parameters))
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class ReplayExecutionAdapter(Protocol):
    """A runtime adapter selected by its versioned persisted name.

    The source execution and frozen replay configuration are host-owned values.
    Plugin code must not import Core models to implement this protocol. External
    adapters return :class:`ReplayExecutionResult`; hosts may retain temporary
    compatibility for their own legacy in-process adapters.
    """

    @property
    def name(self) -> str: ...

    def validate_configuration(
        self, source_execution: object, configuration: object
    ) -> None: ...

    def replay(
        self,
        source_execution: object,
        configuration: object,
        context: ReplayExecutionContext,
    ) -> ReplayExecutionResult: ...


def _required_string(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Replay intervention envelope {name} is required.")
    return value


def _required_version(payload: Mapping[str, object]) -> int:
    value = payload.get("policy_version")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(
            "Replay intervention envelope policy_version must be positive."
        )
    return value
