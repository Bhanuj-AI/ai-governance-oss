"""Deterministic, in-process resolution for execution replay tool calls.

The resolver handles only immutable control metadata. It never invokes a tool,
retrieves private evidence, mutates a replay plan, or contacts a service.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock

from bhanuj_governance_plugin_api.execution_replay import (
    EVIDENCE_RESOLUTION_PLAN_SCHEMA_VERSION,
    EvidenceResolutionPlan,
    ReplayDivergence,
    ReplayDivergenceKind,
    ReplayResolutionOutcome,
    ReplayToolCall,
    ReplayToolCallKind,
    ReplayToolResolution,
)

REPLAY_INTERVENTION_BINDING_SCHEMA_VERSION = "replay-intervention-binding/v1"
REPLAY_RESOLUTION_SUMMARY_SCHEMA_VERSION = "replay-resolution-summary/v1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SHORT_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ExecutionReplayResolverConfigurationError(ValueError):
    """A plan or intervention binding cannot safely start a resolver session."""


class ReplayResolutionReasonCode(StrEnum):
    """Stable, bounded resolver reasons with deterministic precedence."""

    EXACT_RECORDED_MATCH = "EXACT_RECORDED_MATCH"
    APPROVED_INTERVENTION = "APPROVED_INTERVENTION"
    UNOBSERVED_TOOL_CALL = "UNOBSERVED_TOOL_CALL"
    TOOL_IDENTITY_MISMATCH = "TOOL_IDENTITY_MISMATCH"
    ARGUMENT_DIGEST_MISMATCH = "ARGUMENT_DIGEST_MISMATCH"
    DUPLICATE_TOOL_CALL = "DUPLICATE_TOOL_CALL"
    DEPENDENCY_VIOLATION = "DEPENDENCY_VIOLATION"
    UNPLANNED_RETRY = "UNPLANNED_RETRY"
    INTERVENTION_MISMATCH = "INTERVENTION_MISMATCH"
    EVIDENCE_BINDING_INVALID = "EVIDENCE_BINDING_INVALID"
    UNSUPPORTED_DIGEST_ALGORITHM = "UNSUPPORTED_DIGEST_ALGORITHM"
    SESSION_TERMINAL = "SESSION_TERMINAL"


class ReplayResolutionCompletion(StrEnum):
    """Completion applies only to reported governed tool calls."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ReplayInterventionBinding:
    """Minimal plan-bound authorization to select replacement evidence.

    Policy identity, strategy, and payload transformation remain owned by the
    existing intervention contracts and private runtime. This binding contains
    only what a pure resolver needs to select already-authorized evidence.
    """

    replay_manifest_hash: str
    resolution_plan_digest: str
    target_planned_call_id: str
    intervention_digest: str
    replacement_evidence_reference: str
    replacement_response_digest: str
    schema_version: str = REPLAY_INTERVENTION_BINDING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPLAY_INTERVENTION_BINDING_SCHEMA_VERSION:
            raise ValueError("Unsupported replay intervention-binding schema.")
        _require_hex_digest("replay_manifest_hash", self.replay_manifest_hash)
        _require_hex_digest("resolution_plan_digest", self.resolution_plan_digest)
        _require_identifier("target_planned_call_id", self.target_planned_call_id)
        _require_sha256("intervention_digest", self.intervention_digest)
        _require_reference(
            "replacement_evidence_reference", self.replacement_evidence_reference
        )
        _require_sha256("replacement_response_digest", self.replacement_response_digest)

    def to_payload(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "replay_manifest_hash": self.replay_manifest_hash,
            "resolution_plan_digest": self.resolution_plan_digest,
            "target_planned_call_id": self.target_planned_call_id,
            "intervention_digest": self.intervention_digest,
            "replacement_evidence_reference": self.replacement_evidence_reference,
            "replacement_response_digest": self.replacement_response_digest,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayInterventionBinding:
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "replay_manifest_hash",
                "resolution_plan_digest",
                "target_planned_call_id",
                "intervention_digest",
                "replacement_evidence_reference",
                "replacement_response_digest",
            },
            "Replay intervention binding",
        )
        return cls(
            replay_manifest_hash=_required_string(payload, "replay_manifest_hash"),
            resolution_plan_digest=_required_string(payload, "resolution_plan_digest"),
            target_planned_call_id=_required_string(payload, "target_planned_call_id"),
            intervention_digest=_required_string(payload, "intervention_digest"),
            replacement_evidence_reference=_required_string(
                payload, "replacement_evidence_reference"
            ),
            replacement_response_digest=_required_string(
                payload, "replacement_response_digest"
            ),
            schema_version=_required_string(payload, "schema_version"),
        )


@dataclass(frozen=True)
class ReplayResolutionSummary:
    """Deterministic completion state for one resolver session.

    ``COMPLETE`` means each planned, governed call was accounted for. It does
    not claim that an adapter observed all native runtime activity.
    """

    completion: ReplayResolutionCompletion | str
    resolution_plan_digest: str
    consumed_planned_call_ids: tuple[str, ...]
    remaining_planned_call_ids: tuple[str, ...]
    resolution_count: int
    intervention_required: bool
    intervention_applied_call_id: str | None = None
    terminal_reason_code: ReplayResolutionReasonCode | str | None = None
    blocking_divergence_count: int = 0
    schema_version: str = REPLAY_RESOLUTION_SUMMARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPLAY_RESOLUTION_SUMMARY_SCHEMA_VERSION:
            raise ValueError("Unsupported replay resolution-summary schema.")
        completion = ReplayResolutionCompletion(self.completion)
        _require_hex_digest("resolution_plan_digest", self.resolution_plan_digest)
        consumed = _unique_identifiers(
            "consumed_planned_call_ids", self.consumed_planned_call_ids
        )
        remaining = _unique_identifiers(
            "remaining_planned_call_ids", self.remaining_planned_call_ids
        )
        if set(consumed) & set(remaining):
            raise ValueError("Consumed and remaining planned calls must not overlap.")
        if (
            isinstance(self.resolution_count, bool)
            or not isinstance(self.resolution_count, int)
            or self.resolution_count < 0
        ):
            raise ValueError("resolution_count must be a non-negative integer.")
        if not isinstance(self.intervention_required, bool):
            raise TypeError("intervention_required must be boolean.")
        if self.intervention_applied_call_id is not None:
            _require_identifier(
                "intervention_applied_call_id", self.intervention_applied_call_id
            )
            if self.intervention_applied_call_id not in consumed:
                raise ValueError("Applied intervention must reference a consumed call.")
        reason = (
            ReplayResolutionReasonCode(self.terminal_reason_code)
            if self.terminal_reason_code is not None
            else None
        )
        if (
            isinstance(self.blocking_divergence_count, bool)
            or not isinstance(self.blocking_divergence_count, int)
            or self.blocking_divergence_count < 0
        ):
            raise ValueError("blocking_divergence_count must be non-negative.")
        if completion is ReplayResolutionCompletion.COMPLETE and (
            remaining
            or reason is not None
            or self.blocking_divergence_count
            or (
                self.intervention_required and self.intervention_applied_call_id is None
            )
        ):
            raise ValueError("Complete resolution summary has unresolved state.")
        if completion is ReplayResolutionCompletion.FAILED and reason is None:
            raise ValueError("Failed resolution summary requires a terminal reason.")
        if completion is ReplayResolutionCompletion.INCOMPLETE and reason is not None:
            raise ValueError(
                "Incomplete resolution summary cannot carry a terminal reason."
            )
        object.__setattr__(self, "completion", completion)
        object.__setattr__(self, "consumed_planned_call_ids", consumed)
        object.__setattr__(self, "remaining_planned_call_ids", remaining)
        object.__setattr__(self, "terminal_reason_code", reason)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "completion": self.completion.value,
            "resolution_plan_digest": self.resolution_plan_digest,
            "consumed_planned_call_ids": list(self.consumed_planned_call_ids),
            "remaining_planned_call_ids": list(self.remaining_planned_call_ids),
            "resolution_count": self.resolution_count,
            "intervention_required": self.intervention_required,
            "intervention_applied_call_id": self.intervention_applied_call_id,
            "terminal_reason_code": (
                self.terminal_reason_code.value
                if self.terminal_reason_code is not None
                else None
            ),
            "blocking_divergence_count": self.blocking_divergence_count,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayResolutionSummary:
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "completion",
                "resolution_plan_digest",
                "consumed_planned_call_ids",
                "remaining_planned_call_ids",
                "resolution_count",
                "intervention_required",
                "intervention_applied_call_id",
                "terminal_reason_code",
                "blocking_divergence_count",
            },
            "Replay resolution summary",
        )
        return cls(
            completion=_required_string(payload, "completion"),
            resolution_plan_digest=_required_string(payload, "resolution_plan_digest"),
            consumed_planned_call_ids=_string_tuple(
                payload, "consumed_planned_call_ids"
            ),
            remaining_planned_call_ids=_string_tuple(
                payload, "remaining_planned_call_ids"
            ),
            resolution_count=_required_int(payload, "resolution_count"),
            intervention_required=_required_bool(payload, "intervention_required"),
            intervention_applied_call_id=_optional_string(
                payload.get("intervention_applied_call_id")
            ),
            terminal_reason_code=_optional_string(payload.get("terminal_reason_code")),
            blocking_divergence_count=_required_int(
                payload, "blocking_divergence_count"
            ),
            schema_version=_required_string(payload, "schema_version"),
        )


class ExecutionReplayResolver:
    """Lock-protected, deterministic resolver for one immutable replay plan.

    Failure precedence is: terminal session, invalid attempt/digest contract,
    unknown tool, scope/schema mismatch, incompatible argument digest,
    occurrence/retry mismatch, dependency mismatch, duplicate consumption,
    then intervention binding. A first terminal result is retained for
    finalization; later calls receive ``SESSION_TERMINAL`` and cannot consume
    more evidence.
    """

    def __init__(
        self,
        plan: EvidenceResolutionPlan,
        intervention: ReplayInterventionBinding | None = None,
    ) -> None:
        self._plan = _validated_plan(plan)
        self._planned_by_id = {call.call_id: call for call in self._plan.planned_calls}
        self._intervention = _validated_intervention(self._plan, intervention)
        self._consumed_planned_call_ids: set[str] = set()
        self._rejected_attempt_call_ids: set[str] = set()
        self._applied_intervention_call_id: str | None = None
        self._terminal_resolution: ReplayToolResolution | None = None
        self._resolution_count = 0
        self._lock = RLock()

    @property
    def plan(self) -> EvidenceResolutionPlan:
        """Return the immutable plan; the resolver never modifies it."""

        return self._plan

    def resolve(
        self,
        attempted_call: ReplayToolCall,
        *,
        intervention_digest: str | None = None,
    ) -> ReplayToolResolution:
        """Resolve one intercepted call using exact plan identity only.

        ``intervention_digest`` is a binding confirmation from the frozen
        intervention envelope. It never selects replacement evidence itself.
        """

        if not isinstance(attempted_call, ReplayToolCall):
            raise TypeError("attempted_call must be a ReplayToolCall.")
        with self._lock:
            if self._terminal_resolution is not None:
                self._rejected_attempt_call_ids.add(attempted_call.call_id)
                self._resolution_count += 1
                return ReplayToolResolution(
                    attempted_call_id=attempted_call.call_id,
                    outcome=ReplayResolutionOutcome.INVALID,
                    reason_code=ReplayResolutionReasonCode.SESSION_TERMINAL,
                )
            if attempted_call.kind is not ReplayToolCallKind.ATTEMPTED:
                return self._invalidate(
                    attempted_call, ReplayResolutionReasonCode.EVIDENCE_BINDING_INVALID
                )
            if (
                attempted_call.argument_digest.canonicalization_version
                != self._plan.canonicalization_version
                or attempted_call.argument_digest.algorithm
                not in self._plan.capability.argument_digest_algorithms
            ):
                return self._invalidate(
                    attempted_call,
                    ReplayResolutionReasonCode.UNSUPPORTED_DIGEST_ALGORITHM,
                )
            return self._resolve_locked(attempted_call, intervention_digest)

    def _resolve_locked(
        self,
        attempted_call: ReplayToolCall,
        intervention_digest: str | None,
    ) -> ReplayToolResolution:
        planned_calls = self._plan.planned_calls
        same_tool = [
            call
            for call in planned_calls
            if call.tool_symbol == attempted_call.tool_symbol
        ]
        if not same_tool:
            return self._diverge(
                attempted_call, ReplayResolutionReasonCode.UNOBSERVED_TOOL_CALL
            )
        same_scope = [
            call for call in same_tool if call.scope_id == attempted_call.scope_id
        ]
        if not same_scope:
            return self._diverge(
                attempted_call, ReplayResolutionReasonCode.TOOL_IDENTITY_MISMATCH
            )
        same_schema = [
            call
            for call in same_scope
            if call.tool_schema_version == attempted_call.tool_schema_version
        ]
        if not same_schema:
            return self._diverge(
                attempted_call, ReplayResolutionReasonCode.TOOL_IDENTITY_MISMATCH
            )
        same_digest_contract = [
            call
            for call in same_schema
            if call.argument_digest.algorithm
            == attempted_call.argument_digest.algorithm
            and call.argument_digest.canonicalization_version
            == attempted_call.argument_digest.canonicalization_version
        ]
        if not same_digest_contract:
            return self._invalidate(
                attempted_call, ReplayResolutionReasonCode.UNSUPPORTED_DIGEST_ALGORITHM
            )
        same_arguments = [
            call
            for call in same_digest_contract
            if call.argument_digest == attempted_call.argument_digest
        ]
        if not same_arguments:
            return self._diverge(
                attempted_call, ReplayResolutionReasonCode.ARGUMENT_DIGEST_MISMATCH
            )
        same_occurrence = [
            call
            for call in same_arguments
            if call.occurrence == attempted_call.occurrence
        ]
        if not same_occurrence:
            return self._diverge(
                attempted_call, ReplayResolutionReasonCode.TOOL_IDENTITY_MISMATCH
            )
        candidate = same_occurrence[0]
        if candidate.retry_of_call_id != attempted_call.retry_of_call_id:
            return self._diverge(
                attempted_call, ReplayResolutionReasonCode.UNPLANNED_RETRY
            )
        if candidate.dependency_call_ids != attempted_call.dependency_call_ids:
            return self._diverge(
                attempted_call, ReplayResolutionReasonCode.DEPENDENCY_VIOLATION
            )
        if candidate.call_id in self._consumed_planned_call_ids:
            return self._diverge(
                attempted_call, ReplayResolutionReasonCode.DUPLICATE_TOOL_CALL
            )
        if not set(candidate.dependency_call_ids).issubset(
            self._consumed_planned_call_ids
        ):
            return self._diverge(
                attempted_call, ReplayResolutionReasonCode.DEPENDENCY_VIOLATION
            )
        if self._intervention is None:
            if intervention_digest is not None:
                return self._invalidate(
                    attempted_call, ReplayResolutionReasonCode.INTERVENTION_MISMATCH
                )
            return self._record(candidate, attempted_call)
        if candidate.call_id != self._intervention.target_planned_call_id:
            if intervention_digest is not None:
                return self._invalidate(
                    attempted_call, ReplayResolutionReasonCode.INTERVENTION_MISMATCH
                )
            return self._record(candidate, attempted_call)
        if intervention_digest != self._intervention.intervention_digest:
            return self._invalidate(
                attempted_call, ReplayResolutionReasonCode.INTERVENTION_MISMATCH
            )
        return self._intervene(candidate, attempted_call)

    def _record(
        self, planned_call: ReplayToolCall, attempted_call: ReplayToolCall
    ) -> ReplayToolResolution:
        resolution = ReplayToolResolution(
            attempted_call_id=attempted_call.call_id,
            outcome=ReplayResolutionOutcome.RESOLVED_RECORDED,
            reason_code=ReplayResolutionReasonCode.EXACT_RECORDED_MATCH,
            planned_call_id=planned_call.call_id,
            selected_evidence_reference=planned_call.evidence_reference,
            selected_response_digest=planned_call.response_digest,
        )
        self._consumed_planned_call_ids.add(planned_call.call_id)
        self._resolution_count += 1
        return resolution

    def _intervene(
        self, planned_call: ReplayToolCall, attempted_call: ReplayToolCall
    ) -> ReplayToolResolution:
        assert self._intervention is not None
        if self._applied_intervention_call_id is not None:
            return self._diverge(
                attempted_call, ReplayResolutionReasonCode.DUPLICATE_TOOL_CALL
            )
        resolution = ReplayToolResolution(
            attempted_call_id=attempted_call.call_id,
            outcome=ReplayResolutionOutcome.RESOLVED_INTERVENTION,
            reason_code=ReplayResolutionReasonCode.APPROVED_INTERVENTION,
            planned_call_id=planned_call.call_id,
            selected_evidence_reference=self._intervention.replacement_evidence_reference,
            selected_response_digest=self._intervention.replacement_response_digest,
        )
        self._consumed_planned_call_ids.add(planned_call.call_id)
        self._applied_intervention_call_id = planned_call.call_id
        self._resolution_count += 1
        return resolution

    def _diverge(
        self,
        attempted_call: ReplayToolCall,
        reason: ReplayResolutionReasonCode,
    ) -> ReplayToolResolution:
        divergence = ReplayDivergence(
            code=reason.value,
            kind=ReplayDivergenceKind.TOOL_CALL,
            blocking=True,
            attempted_call_id=attempted_call.call_id,
            scope_id=attempted_call.scope_id,
            safe_diagnostics={"reason": reason.value},
        )
        resolution = ReplayToolResolution(
            attempted_call_id=attempted_call.call_id,
            outcome=ReplayResolutionOutcome.DIVERGED,
            reason_code=reason,
            divergence=divergence,
        )
        self._terminal_resolution = resolution
        self._rejected_attempt_call_ids.add(attempted_call.call_id)
        self._resolution_count += 1
        return resolution

    def _invalidate(
        self,
        attempted_call: ReplayToolCall,
        reason: ReplayResolutionReasonCode,
    ) -> ReplayToolResolution:
        resolution = ReplayToolResolution(
            attempted_call_id=attempted_call.call_id,
            outcome=ReplayResolutionOutcome.INVALID,
            reason_code=reason,
        )
        self._terminal_resolution = resolution
        self._rejected_attempt_call_ids.add(attempted_call.call_id)
        self._resolution_count += 1
        return resolution

    def finalize(self) -> ReplayResolutionSummary:
        """Return deterministic resolver completeness, without execution coverage claims."""

        with self._lock:
            consumed = tuple(sorted(self._consumed_planned_call_ids))
            remaining = tuple(
                call_id
                for call_id in sorted(self._planned_by_id)
                if call_id not in self._consumed_planned_call_ids
            )
            intervention_required = self._intervention is not None
            if self._terminal_resolution is not None:
                return ReplayResolutionSummary(
                    completion=ReplayResolutionCompletion.FAILED,
                    resolution_plan_digest=self._plan.plan_digest,
                    consumed_planned_call_ids=consumed,
                    remaining_planned_call_ids=remaining,
                    resolution_count=self._resolution_count,
                    intervention_required=intervention_required,
                    intervention_applied_call_id=self._applied_intervention_call_id,
                    terminal_reason_code=self._terminal_resolution.reason_code,
                    blocking_divergence_count=(
                        1
                        if self._terminal_resolution.outcome
                        is ReplayResolutionOutcome.DIVERGED
                        else 0
                    ),
                )
            if remaining or (
                intervention_required and self._applied_intervention_call_id is None
            ):
                return ReplayResolutionSummary(
                    completion=ReplayResolutionCompletion.INCOMPLETE,
                    resolution_plan_digest=self._plan.plan_digest,
                    consumed_planned_call_ids=consumed,
                    remaining_planned_call_ids=remaining,
                    resolution_count=self._resolution_count,
                    intervention_required=intervention_required,
                    intervention_applied_call_id=self._applied_intervention_call_id,
                )
            return ReplayResolutionSummary(
                completion=ReplayResolutionCompletion.COMPLETE,
                resolution_plan_digest=self._plan.plan_digest,
                consumed_planned_call_ids=consumed,
                remaining_planned_call_ids=remaining,
                resolution_count=self._resolution_count,
                intervention_required=intervention_required,
                intervention_applied_call_id=self._applied_intervention_call_id,
            )


def _validated_plan(plan: EvidenceResolutionPlan) -> EvidenceResolutionPlan:
    if not isinstance(plan, EvidenceResolutionPlan):
        raise ExecutionReplayResolverConfigurationError(
            "Resolver requires an EvidenceResolutionPlan."
        )
    try:
        verified = EvidenceResolutionPlan.from_payload(plan.to_payload())
    except (TypeError, ValueError) as error:
        raise ExecutionReplayResolverConfigurationError(
            "Resolution plan is malformed or fails its integrity digest."
        ) from error
    if verified.schema_version != EVIDENCE_RESOLUTION_PLAN_SCHEMA_VERSION:
        raise ExecutionReplayResolverConfigurationError(
            "Resolution plan schema is unsupported."
        )
    return verified


def _validated_intervention(
    plan: EvidenceResolutionPlan,
    intervention: ReplayInterventionBinding | None,
) -> ReplayInterventionBinding | None:
    if intervention is None:
        return None
    if not isinstance(intervention, ReplayInterventionBinding):
        raise ExecutionReplayResolverConfigurationError(
            "Resolver intervention must be a ReplayInterventionBinding."
        )
    if intervention.replay_manifest_hash != plan.replay_manifest_hash:
        raise ExecutionReplayResolverConfigurationError(
            "Intervention binding does not match the replay manifest."
        )
    if intervention.resolution_plan_digest != plan.plan_digest:
        raise ExecutionReplayResolverConfigurationError(
            "Intervention binding does not match the resolution plan."
        )
    if intervention.target_planned_call_id not in {
        call.call_id for call in plan.planned_calls
    }:
        raise ExecutionReplayResolverConfigurationError(
            "Intervention target is not an authorised planned call."
        )
    return intervention


def _require_exact_keys(
    payload: Mapping[str, object], expected: set[str], name: str
) -> None:
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise ValueError(f"{name} payload has an unsupported shape.")


def _required_string(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Optional value must be a string.")
    return value


def _required_int(payload: Mapping[str, object], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    return value


def _required_bool(payload: Mapping[str, object], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be boolean.")
    return value


def _string_tuple(payload: Mapping[str, object], name: str) -> tuple[str, ...]:
    value = payload.get(name)
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) for item in value
    ):
        raise TypeError(f"{name} must be a list of strings.")
    return tuple(value)


def _require_identifier(name: str, value: object) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier.")


def _require_short_identifier(name: str, value: object) -> None:
    if not isinstance(value, str) or not _SHORT_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier.")


def _require_hex_digest(name: str, value: object) -> None:
    if not isinstance(value, str) or not _HEX_SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a SHA-256 hex digest.")


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a sha256 digest.")


def _require_reference(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError(f"{name} must be a bounded non-blank reference.")


def _unique_identifiers(name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    items = tuple(values)
    for value in items:
        _require_identifier(name, value)
    if len(items) != len(set(items)):
        raise ValueError(f"{name} must be unique.")
    return tuple(sorted(items))
