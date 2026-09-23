"""Provider-neutral contracts for isolated, governed Replay execution.

External runtimes receive only frozen replay configuration and a bounded
intervention envelope.  The envelope intentionally excludes prompts, model
responses, tool arguments, tool results, and reasoning.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from ai_governance.domain.replay import (
    ControlledEvidenceIntervention,
    ControlledEvidenceStrategy,
    ReplayConfiguration,
)
from ai_governance.domain.workflow_execution import WorkflowExecution

REPLAY_INTERVENTION_ENVELOPE_SCHEMA_VERSION = "replay-intervention-envelope/v1"


class ReplayCancellationToken(Protocol):
    """Cooperative cancellation visible to an adapter at safe boundaries."""

    @property
    def is_cancelled(self) -> bool: ...


@dataclass(frozen=True)
class ReplayInterventionEnvelope:
    """Policy-authorized, reference-only data for one controlled replay.

    ``counterfactual_reference`` is resolved by the external runtime under its
    own isolation boundary.  Core proves the selected policy and requested
    artifact without materialising the underlying evidence.
    """

    policy_id: str
    policy_version: int
    external_execution_id: str
    runtime_tool_call_id: str
    intervention_provider: str
    intervention_provider_version: str
    strategy: ControlledEvidenceStrategy
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
        if self.policy_version < 1:
            raise ValueError(
                "Replay intervention envelope policy_version must be positive."
            )
        if self.schema_version != REPLAY_INTERVENTION_ENVELOPE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported Replay intervention envelope schema version: {self.schema_version!r}."
            )

    def to_payload(self) -> dict[str, object]:
        """Serialise the fixed, reference-only envelope for an external runtime."""
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "external_execution_id": self.external_execution_id,
            "runtime_tool_call_id": self.runtime_tool_call_id,
            "intervention_provider": self.intervention_provider,
            "intervention_provider_version": self.intervention_provider_version,
            "strategy": self.strategy.value,
            "original_evidence_digest": self.original_evidence_digest,
            "counterfactual_reference": self.counterfactual_reference,
            "counterfactual_digest": self.counterfactual_digest,
            "intervention_digest": self.intervention_digest,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayInterventionEnvelope:
        """Parse only the v1 wire shape and reject unknown or missing fields."""
        expected = set(cls.__dataclass_fields__)
        if set(payload) != expected:
            raise ValueError(
                "Replay intervention envelope payload has an unsupported shape."
            )
        version = payload.get("schema_version")
        if version != REPLAY_INTERVENTION_ENVELOPE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported Replay intervention envelope schema version: {version!r}."
            )
        strategy = payload.get("strategy")
        try:
            return cls(
                policy_id=_required_payload_string(payload, "policy_id"),
                policy_version=_required_payload_version(payload),
                external_execution_id=_required_payload_string(
                    payload, "external_execution_id"
                ),
                runtime_tool_call_id=_required_payload_string(
                    payload, "runtime_tool_call_id"
                ),
                intervention_provider=_required_payload_string(
                    payload, "intervention_provider"
                ),
                intervention_provider_version=_required_payload_string(
                    payload, "intervention_provider_version"
                ),
                strategy=ControlledEvidenceStrategy(strategy),
                original_evidence_digest=_required_payload_string(
                    payload, "original_evidence_digest"
                ),
                counterfactual_reference=_required_payload_string(
                    payload, "counterfactual_reference"
                ),
                counterfactual_digest=_required_payload_string(
                    payload, "counterfactual_digest"
                ),
                intervention_digest=_required_payload_string(
                    payload, "intervention_digest"
                ),
                schema_version=REPLAY_INTERVENTION_ENVELOPE_SCHEMA_VERSION,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Replay intervention envelope payload is invalid."
            ) from error


def _required_payload_string(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Replay intervention envelope {name} is required.")
    return value


def _required_payload_version(payload: Mapping[str, object]) -> int:
    value = payload.get("policy_version")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(
            "Replay intervention envelope policy_version must be positive."
        )
    return value


@dataclass(frozen=True)
class ReplayExecutionContext:
    """Immutable inputs supplied to an execution adapter for one job attempt.

    ``new_execution_id`` is reserved by the replay aggregate before adapter
    invocation. Adapters must return that exact identity and should consult the
    cancellation token at safe runtime boundaries. ``metadata`` is an adapter
    extension point; durable lineage is added by the handler after execution.
    """

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
    metadata: dict[str, Any]
    controlled_evidence_intervention: ControlledEvidenceIntervention | None = None
    intervention_envelope: ReplayInterventionEnvelope | None = None


class ReplayExecutionAdapter(Protocol):
    """Adapter boundary for reconstructing one frozen workflow execution.

    Implementations validate replay-specific runtime requirements before
    running and must return a new ``WorkflowExecution`` with the reserved ID.
    They never persist the execution or mutate the source; the Replay handler
    retains that responsibility so lineage stays consistent across adapters.
    """

    @property
    def name(self) -> str: ...

    def validate_configuration(
        self, source_execution: WorkflowExecution, configuration: ReplayConfiguration
    ) -> None: ...

    def replay(
        self,
        source_execution: WorkflowExecution,
        configuration: ReplayConfiguration,
        context: ReplayExecutionContext,
    ) -> WorkflowExecution: ...


__all__ = [
    "REPLAY_INTERVENTION_ENVELOPE_SCHEMA_VERSION",
    "ReplayCancellationToken",
    "ReplayExecutionAdapter",
    "ReplayExecutionContext",
    "ReplayInterventionEnvelope",
]
