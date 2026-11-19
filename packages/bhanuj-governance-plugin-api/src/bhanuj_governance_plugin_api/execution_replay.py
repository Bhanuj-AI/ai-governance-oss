"""Versioned, reference-only contracts for verified execution replay.

These types deliberately describe captured evidence and an adapter's bounded
report of execution.  They do *not* resolve a call, intercept a runtime, or
provide a sandbox.  Those are later responsibilities of a shared resolver,
runtime adapters, and the Replay worker respectively.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol

EXECUTION_REPLAY_CAPABILITY_SCHEMA_VERSION = "execution-replay-capability/v1"
REPLAY_TOOL_CALL_SCHEMA_VERSION = "replay-tool-call/v1"
EVIDENCE_RESOLUTION_PLAN_SCHEMA_VERSION = "evidence-resolution-plan/v1"
REPLAY_TOOL_RESOLUTION_SCHEMA_VERSION = "replay-tool-resolution/v1"
REPLAY_DIVERGENCE_SCHEMA_VERSION = "replay-divergence/v1"
REPLAY_EXECUTION_TRACE_SCHEMA_VERSION = "replay-execution-trace/v1"
REPLAY_EXECUTION_ATTESTATION_SCHEMA_VERSION = "replay-execution-attestation/v1"
CANONICAL_TOOL_IDENTITY_VERSION = "canonical-tool-identity/v1"
CANONICAL_TOOL_ARGUMENTS_VERSION = "canonical-tool-arguments/v1"
EVIDENCE_ONLY_REPLAY_SAFETY_SCHEMA_VERSION = "evidence-only-replay-safety/v1"

MAX_PLAN_CALLS = 256
MAX_TRACE_CALLS = 1_024
MAX_DEPENDENCIES = 64
MAX_BOUNDARIES = 32
MAX_DIVERGENCES = 256
MAX_SAFE_DIAGNOSTICS = 16

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SHORT_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MANIFEST_HASH = re.compile(r"^[0-9a-f]{64}$")
_SAFE_METADATA_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SENSITIVE_NAMES = frozenset(
    {
        "arguments",
        "credential",
        "credentials",
        "message",
        "messages",
        "payload",
        "prompt",
        "response",
        "result",
        "secret",
        "token",
    }
)


class ToolArgumentDigestAlgorithm(StrEnum):
    """Algorithms permitted for a canonical tool-argument fingerprint."""

    SHA256_JSON_V1 = "sha256-json/v1"
    HMAC_SHA256_JSON_V1 = "hmac-sha256-json/v1"


class ReplayToolCallKind(StrEnum):
    """Whether a tool call is frozen historical evidence or a live attempt."""

    PLANNED = "PLANNED"
    ATTEMPTED = "ATTEMPTED"


class ReplayResolutionOutcome(StrEnum):
    """A resolver outcome; this is not a Replay lifecycle state."""

    RESOLVED_RECORDED = "RESOLVED_RECORDED"
    RESOLVED_INTERVENTION = "RESOLVED_INTERVENTION"
    DIVERGED = "DIVERGED"
    INVALID = "INVALID"


class ReplayDivergenceKind(StrEnum):
    TOOL_CALL = "TOOL_CALL"
    TOOL_FREE_BRANCH = "TOOL_FREE_BRANCH"


class ReplayExecutionPathCoverage(StrEnum):
    """What the adapter claims to have observed at declared boundaries."""

    COMPLETE_DECLARED_BOUNDARIES = "COMPLETE_DECLARED_BOUNDARIES"
    PARTIAL_DECLARED_BOUNDARIES = "PARTIAL_DECLARED_BOUNDARIES"
    UNSUPPORTED_SURFACE = "UNSUPPORTED_SURFACE"


class ToolArgumentDigestKeyProvider(Protocol):
    """Runtime-owned source of a tenant-scoped HMAC key.

    The key and its storage never cross this Plugin API boundary.  Returning
    ``None`` is an explicit unavailable-key failure, not permission to fall
    back to an unhashed or differently hashed value.
    """

    def get_key(
        self,
        *,
        organization_id: str,
        project_id: str,
        key_version: str,
    ) -> bytes | None: ...


class ToolArgumentDigestConfigurationError(ValueError):
    """A requested digest algorithm lacks valid runtime-owned key material."""


def canonical_tool_arguments_json(arguments: Mapping[str, Any]) -> str:
    """Return the stable JSON form used by the public replay identity contract.

    The rules intentionally match the existing Runtime Action Authorization
    canonical JSON rules while remaining dependency-free from that subsystem.
    """

    if not isinstance(arguments, Mapping):
        raise TypeError("tool arguments must be a mapping.")
    try:
        return json.dumps(
            dict(arguments), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as error:
        raise ValueError("tool arguments must be JSON-canonicalizable.") from error


@dataclass(frozen=True)
class ToolArgumentDigest:
    """A non-secret canonical argument fingerprint and its reproducibility data."""

    algorithm: ToolArgumentDigestAlgorithm | str
    digest: str
    canonicalization_version: str = CANONICAL_TOOL_ARGUMENTS_VERSION
    key_version: str | None = None

    def __post_init__(self) -> None:
        algorithm = ToolArgumentDigestAlgorithm(self.algorithm)
        if self.canonicalization_version != CANONICAL_TOOL_ARGUMENTS_VERSION:
            raise ValueError("Unsupported canonical tool-arguments version.")
        _require_sha256("tool argument digest", self.digest)
        if algorithm is ToolArgumentDigestAlgorithm.HMAC_SHA256_JSON_V1:
            _require_short_identifier(
                "tool argument digest key_version", self.key_version
            )
        elif self.key_version is not None:
            raise ValueError("Unkeyed tool argument digests cannot carry key_version.")
        object.__setattr__(self, "algorithm", algorithm)

    def to_payload(self) -> dict[str, object]:
        return {
            "algorithm": self.algorithm.value,
            "digest": self.digest,
            "canonicalization_version": self.canonicalization_version,
            "key_version": self.key_version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ToolArgumentDigest:
        _require_exact_keys(
            payload,
            {"algorithm", "digest", "canonicalization_version", "key_version"},
            "Tool argument digest",
        )
        return cls(
            algorithm=_required_string(payload, "algorithm"),
            digest=_required_string(payload, "digest"),
            canonicalization_version=_required_string(
                payload, "canonicalization_version"
            ),
            key_version=_optional_string(payload.get("key_version")),
        )


def create_tool_argument_digest(
    arguments: Mapping[str, Any],
    *,
    algorithm: ToolArgumentDigestAlgorithm | str,
    organization_id: str | None = None,
    project_id: str | None = None,
    key_version: str | None = None,
    key_provider: ToolArgumentDigestKeyProvider | None = None,
) -> ToolArgumentDigest:
    """Create a reproducible digest without retaining argument values or keys.

    ``SHA256_JSON_V1`` exists for integrations whose argument values are known
    not to be sensitive.  New persisted sensitive fingerprints should use the
    HMAC variant, supplied by the runtime's tenant-scoped key provider.
    """

    selected = ToolArgumentDigestAlgorithm(algorithm)
    encoded = canonical_tool_arguments_json(arguments).encode("utf-8")
    if selected is ToolArgumentDigestAlgorithm.SHA256_JSON_V1:
        if key_version is not None or key_provider is not None:
            raise ToolArgumentDigestConfigurationError(
                "Unkeyed tool argument digest does not accept key configuration."
            )
        digest = hashlib.sha256(encoded).hexdigest()
        return ToolArgumentDigest(selected, f"sha256:{digest}")

    if organization_id is None or project_id is None:
        raise ToolArgumentDigestConfigurationError(
            "Keyed tool argument digest requires organization and project bindings."
        )
    _require_identifier("organization_id", organization_id)
    _require_identifier("project_id", project_id)
    _require_short_identifier("tool argument digest key_version", key_version)
    if key_provider is None:
        raise ToolArgumentDigestConfigurationError(
            "Keyed tool argument digest requires a key provider."
        )
    key = key_provider.get_key(
        organization_id=organization_id,
        project_id=project_id,
        key_version=key_version,
    )
    if not isinstance(key, bytes) or not key:
        raise ToolArgumentDigestConfigurationError(
            "Keyed tool argument digest key is unavailable or invalid."
        )
    digest = hmac.new(key, encoded, hashlib.sha256).hexdigest()
    return ToolArgumentDigest(
        selected,
        f"sha256:{digest}",
        key_version=key_version,
    )


@dataclass(frozen=True)
class ExecutionReplayCapability:
    """What an adapter can observe and safely replay at declared boundaries.

    It intentionally says nothing about a sandbox, arbitrary application code,
    or the absence of side effects outside those declared boundaries.
    """

    supported_tool_boundaries: tuple[str, ...]
    unsupported_execution_surfaces: tuple[str, ...]
    argument_digest_algorithms: tuple[ToolArgumentDigestAlgorithm | str, ...]
    max_trace_size: int
    supports_async_tools: bool
    supports_subgraphs: bool
    supports_retries: bool
    supports_concurrent_execution: bool
    evidence_only: bool
    no_original_tool_fallback: bool
    canonical_tool_identity_version: str = CANONICAL_TOOL_IDENTITY_VERSION
    canonicalization_version: str = CANONICAL_TOOL_ARGUMENTS_VERSION
    schema_version: str = EXECUTION_REPLAY_CAPABILITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EXECUTION_REPLAY_CAPABILITY_SCHEMA_VERSION:
            raise ValueError("Unsupported execution replay capability schema.")
        if self.canonical_tool_identity_version != CANONICAL_TOOL_IDENTITY_VERSION:
            raise ValueError("Unsupported canonical tool identity version.")
        if self.canonicalization_version != CANONICAL_TOOL_ARGUMENTS_VERSION:
            raise ValueError("Unsupported canonical tool-arguments version.")
        boundaries = _unique_bounded_identifiers(
            "supported_tool_boundaries",
            self.supported_tool_boundaries,
            MAX_BOUNDARIES,
            minimum=1,
        )
        unsupported = _unique_bounded_identifiers(
            "unsupported_execution_surfaces",
            self.unsupported_execution_surfaces,
            MAX_BOUNDARIES,
        )
        if set(boundaries) & set(unsupported):
            raise ValueError("Supported and unsupported execution surfaces overlap.")
        algorithms = tuple(
            ToolArgumentDigestAlgorithm(value)
            for value in self.argument_digest_algorithms
        )
        if not algorithms or len(set(algorithms)) != len(algorithms):
            raise ValueError(
                "Capability digest algorithms must be non-empty and unique."
            )
        if (
            isinstance(self.max_trace_size, bool)
            or not isinstance(self.max_trace_size, int)
            or not 1 <= self.max_trace_size <= MAX_TRACE_CALLS
        ):
            raise ValueError(f"max_trace_size must be between 1 and {MAX_TRACE_CALLS}.")
        if not self.evidence_only or not self.no_original_tool_fallback:
            raise ValueError(
                "Execution replay requires evidence-only and no-original-tool-fallback."
            )
        object.__setattr__(self, "supported_tool_boundaries", boundaries)
        object.__setattr__(self, "unsupported_execution_surfaces", unsupported)
        object.__setattr__(self, "argument_digest_algorithms", algorithms)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "supported_tool_boundaries": list(self.supported_tool_boundaries),
            "unsupported_execution_surfaces": list(self.unsupported_execution_surfaces),
            "canonical_tool_identity_version": self.canonical_tool_identity_version,
            "canonicalization_version": self.canonicalization_version,
            "argument_digest_algorithms": [
                value.value for value in self.argument_digest_algorithms
            ],
            "max_trace_size": self.max_trace_size,
            "supports_async_tools": self.supports_async_tools,
            "supports_subgraphs": self.supports_subgraphs,
            "supports_retries": self.supports_retries,
            "supports_concurrent_execution": self.supports_concurrent_execution,
            "evidence_only": self.evidence_only,
            "no_original_tool_fallback": self.no_original_tool_fallback,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ExecutionReplayCapability:
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "supported_tool_boundaries",
                "unsupported_execution_surfaces",
                "canonical_tool_identity_version",
                "canonicalization_version",
                "argument_digest_algorithms",
                "max_trace_size",
                "supports_async_tools",
                "supports_subgraphs",
                "supports_retries",
                "supports_concurrent_execution",
                "evidence_only",
                "no_original_tool_fallback",
            },
            "Execution replay capability",
        )
        return cls(
            supported_tool_boundaries=_string_tuple(
                payload, "supported_tool_boundaries"
            ),
            unsupported_execution_surfaces=_string_tuple(
                payload, "unsupported_execution_surfaces"
            ),
            argument_digest_algorithms=_string_tuple(
                payload, "argument_digest_algorithms"
            ),
            max_trace_size=_required_int(payload, "max_trace_size"),
            supports_async_tools=_required_bool(payload, "supports_async_tools"),
            supports_subgraphs=_required_bool(payload, "supports_subgraphs"),
            supports_retries=_required_bool(payload, "supports_retries"),
            supports_concurrent_execution=_required_bool(
                payload, "supports_concurrent_execution"
            ),
            evidence_only=_required_bool(payload, "evidence_only"),
            no_original_tool_fallback=_required_bool(
                payload, "no_original_tool_fallback"
            ),
            canonical_tool_identity_version=_required_string(
                payload, "canonical_tool_identity_version"
            ),
            canonicalization_version=_required_string(
                payload, "canonicalization_version"
            ),
            schema_version=_required_string(payload, "schema_version"),
        )


@dataclass(frozen=True)
class ReplayToolCall:
    """Bounded normalized identity for one planned or intercepted tool call."""

    call_id: str
    kind: ReplayToolCallKind | str
    scope_id: str
    tool_symbol: str
    tool_schema_version: str
    argument_digest: ToolArgumentDigest
    occurrence: int
    dependency_call_ids: tuple[str, ...] = ()
    retry_of_call_id: str | None = None
    evidence_reference: str | None = None
    response_digest: str | None = None
    schema_version: str = REPLAY_TOOL_CALL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPLAY_TOOL_CALL_SCHEMA_VERSION:
            raise ValueError("Unsupported replay tool-call schema.")
        kind = ReplayToolCallKind(self.kind)
        for name, value in (
            ("call_id", self.call_id),
            ("scope_id", self.scope_id),
            ("tool_symbol", self.tool_symbol),
            ("tool_schema_version", self.tool_schema_version),
        ):
            _require_identifier(name, value)
        if not isinstance(self.argument_digest, ToolArgumentDigest):
            raise TypeError("argument_digest must be a ToolArgumentDigest.")
        if isinstance(self.occurrence, bool) or not isinstance(self.occurrence, int):
            raise TypeError("occurrence must be an integer.")
        if self.occurrence < 1:
            raise ValueError("occurrence must be positive.")
        dependencies = _unique_bounded_identifiers(
            "dependency_call_ids", self.dependency_call_ids, MAX_DEPENDENCIES
        )
        if self.call_id in dependencies:
            raise ValueError("A tool call cannot depend on itself.")
        if self.retry_of_call_id is not None:
            _require_identifier("retry_of_call_id", self.retry_of_call_id)
            if self.retry_of_call_id == self.call_id:
                raise ValueError("A tool call cannot retry itself.")
        if kind is ReplayToolCallKind.PLANNED:
            _require_bounded_reference("evidence_reference", self.evidence_reference)
            _require_sha256("response_digest", self.response_digest)
        elif self.evidence_reference is not None or self.response_digest is not None:
            raise ValueError("Attempted tool calls cannot carry historical evidence.")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "dependency_call_ids", dependencies)

    @property
    def identity_key(self) -> tuple[str, str, str, str, str, str, str | None, int]:
        """Framework-neutral matching inputs, excluding scheduler timing."""

        return (
            self.scope_id,
            self.tool_symbol,
            self.tool_schema_version,
            self.argument_digest.algorithm.value,
            self.argument_digest.canonicalization_version,
            self.argument_digest.digest,
            self.argument_digest.key_version,
            self.occurrence,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "call_id": self.call_id,
            "kind": self.kind.value,
            "scope_id": self.scope_id,
            "tool_symbol": self.tool_symbol,
            "tool_schema_version": self.tool_schema_version,
            "argument_digest": self.argument_digest.to_payload(),
            "occurrence": self.occurrence,
            "dependency_call_ids": list(self.dependency_call_ids),
            "retry_of_call_id": self.retry_of_call_id,
            "evidence_reference": self.evidence_reference,
            "response_digest": self.response_digest,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayToolCall:
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "call_id",
                "kind",
                "scope_id",
                "tool_symbol",
                "tool_schema_version",
                "argument_digest",
                "occurrence",
                "dependency_call_ids",
                "retry_of_call_id",
                "evidence_reference",
                "response_digest",
            },
            "Replay tool call",
        )
        argument_digest = payload.get("argument_digest")
        if not isinstance(argument_digest, Mapping):
            raise TypeError("Replay tool call argument_digest must be a mapping.")
        return cls(
            call_id=_required_string(payload, "call_id"),
            kind=_required_string(payload, "kind"),
            scope_id=_required_string(payload, "scope_id"),
            tool_symbol=_required_string(payload, "tool_symbol"),
            tool_schema_version=_required_string(payload, "tool_schema_version"),
            argument_digest=ToolArgumentDigest.from_payload(argument_digest),
            occurrence=_required_int(payload, "occurrence"),
            dependency_call_ids=_string_tuple(payload, "dependency_call_ids"),
            retry_of_call_id=_optional_string(payload.get("retry_of_call_id")),
            evidence_reference=_optional_string(payload.get("evidence_reference")),
            response_digest=_optional_string(payload.get("response_digest")),
            schema_version=_required_string(payload, "schema_version"),
        )


@dataclass(frozen=True)
class ReplayEvidenceBinding:
    """The evidence a frozen planned call may materialise privately."""

    call_id: str
    evidence_reference: str
    response_digest: str

    def __post_init__(self) -> None:
        _require_identifier("call_id", self.call_id)
        _require_bounded_reference("evidence_reference", self.evidence_reference)
        _require_sha256("response_digest", self.response_digest)

    def to_payload(self) -> dict[str, str]:
        return {
            "call_id": self.call_id,
            "evidence_reference": self.evidence_reference,
            "response_digest": self.response_digest,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayEvidenceBinding:
        _require_exact_keys(
            payload,
            {"call_id", "evidence_reference", "response_digest"},
            "Replay evidence binding",
        )
        return cls(
            call_id=_required_string(payload, "call_id"),
            evidence_reference=_required_string(payload, "evidence_reference"),
            response_digest=_required_string(payload, "response_digest"),
        )


@dataclass(frozen=True)
class EvidenceResolutionPlan:
    """Frozen authorised historical calls and private-evidence bindings."""

    organization_id: str
    project_id: str
    source_execution_id: str
    replay_manifest_hash: str
    capability: ExecutionReplayCapability
    planned_calls: tuple[ReplayToolCall, ...]
    evidence_bindings: tuple[ReplayEvidenceBinding, ...]
    canonicalization_version: str = CANONICAL_TOOL_ARGUMENTS_VERSION
    plan_digest: str = ""
    schema_version: str = EVIDENCE_RESOLUTION_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EVIDENCE_RESOLUTION_PLAN_SCHEMA_VERSION:
            raise ValueError("Unsupported evidence-resolution plan schema.")
        for name, value in (
            ("organization_id", self.organization_id),
            ("project_id", self.project_id),
            ("source_execution_id", self.source_execution_id),
        ):
            _require_identifier(name, value)
        _require_manifest_hash("replay_manifest_hash", self.replay_manifest_hash)
        if self.canonicalization_version != CANONICAL_TOOL_ARGUMENTS_VERSION:
            raise ValueError("Unsupported plan canonicalization version.")
        if not isinstance(self.capability, ExecutionReplayCapability):
            raise TypeError("capability must be an ExecutionReplayCapability.")
        if self.capability.canonicalization_version != self.canonicalization_version:
            raise ValueError("Plan canonicalization must match its capability.")
        calls = tuple(sorted(self.planned_calls, key=lambda call: call.call_id))
        if len(calls) > MAX_PLAN_CALLS:
            raise ValueError(f"A plan can contain at most {MAX_PLAN_CALLS} calls.")
        if not all(isinstance(call, ReplayToolCall) for call in calls):
            raise TypeError("planned_calls must contain ReplayToolCall values.")
        if any(call.kind is not ReplayToolCallKind.PLANNED for call in calls):
            raise ValueError(
                "Evidence-resolution plans can contain only planned calls."
            )
        if any(
            call.argument_digest.canonicalization_version
            != self.canonicalization_version
            or call.argument_digest.algorithm
            not in self.capability.argument_digest_algorithms
            for call in calls
        ):
            raise ValueError(
                "Plan tool-call argument digests must match the declared capability."
            )
        call_ids = [call.call_id for call in calls]
        if len(set(call_ids)) != len(call_ids):
            raise ValueError("Plan call identities must be unique.")
        identity_keys = [call.identity_key for call in calls]
        if len(set(identity_keys)) != len(identity_keys):
            raise ValueError("Plan tool-call identities must be unique within a scope.")
        known_call_ids = set(call_ids)
        for call in calls:
            if not set(call.dependency_call_ids).issubset(known_call_ids):
                raise ValueError("Plan dependency references an unknown call.")
            if call.retry_of_call_id is not None:
                if call.retry_of_call_id not in known_call_ids:
                    raise ValueError("Plan retry references an unknown call.")
                original = next(
                    item for item in calls if item.call_id == call.retry_of_call_id
                )
                if (
                    original.scope_id,
                    original.tool_symbol,
                    original.tool_schema_version,
                    original.argument_digest,
                ) != (
                    call.scope_id,
                    call.tool_symbol,
                    call.tool_schema_version,
                    call.argument_digest,
                ):
                    raise ValueError("A retry must retain its original tool identity.")
        _validate_acyclic_dependencies(calls)
        bindings = tuple(sorted(self.evidence_bindings, key=lambda item: item.call_id))
        if not all(isinstance(item, ReplayEvidenceBinding) for item in bindings):
            raise TypeError(
                "evidence_bindings must contain ReplayEvidenceBinding values."
            )
        if (
            len(bindings) != len(calls)
            or {item.call_id for item in bindings} != known_call_ids
        ):
            raise ValueError("Plan evidence bindings must exactly cover planned calls.")
        if len({item.call_id for item in bindings}) != len(bindings):
            raise ValueError("Plan evidence bindings must have unique call identities.")
        expected_bindings = {
            call.call_id: (call.evidence_reference, call.response_digest)
            for call in calls
        }
        if any(
            expected_bindings[item.call_id]
            != (item.evidence_reference, item.response_digest)
            for item in bindings
        ):
            raise ValueError("Plan evidence bindings must match planned-call evidence.")
        payload = self._payload_without_digest(calls, bindings)
        digest = _payload_digest(payload)
        if self.plan_digest and self.plan_digest != digest:
            raise ValueError(
                "Evidence-resolution plan digest does not match its content."
            )
        object.__setattr__(self, "planned_calls", calls)
        object.__setattr__(self, "evidence_bindings", bindings)
        object.__setattr__(self, "plan_digest", digest)

    def _payload_without_digest(
        self,
        calls: tuple[ReplayToolCall, ...] | None = None,
        bindings: tuple[ReplayEvidenceBinding, ...] | None = None,
    ) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "organization_id": self.organization_id,
            "project_id": self.project_id,
            "source_execution_id": self.source_execution_id,
            "replay_manifest_hash": self.replay_manifest_hash,
            "capability": self.capability.to_payload(),
            "canonicalization_version": self.canonicalization_version,
            "planned_calls": [
                call.to_payload() for call in (calls or self.planned_calls)
            ],
            "evidence_bindings": [
                binding.to_payload() for binding in (bindings or self.evidence_bindings)
            ],
        }

    def to_payload(self) -> dict[str, object]:
        return {**self._payload_without_digest(), "plan_digest": self.plan_digest}

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> EvidenceResolutionPlan:
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "organization_id",
                "project_id",
                "source_execution_id",
                "replay_manifest_hash",
                "capability",
                "canonicalization_version",
                "planned_calls",
                "evidence_bindings",
                "plan_digest",
            },
            "Evidence-resolution plan",
        )
        capability = payload.get("capability")
        if not isinstance(capability, Mapping):
            raise TypeError("Plan capability must be a mapping.")
        return cls(
            organization_id=_required_string(payload, "organization_id"),
            project_id=_required_string(payload, "project_id"),
            source_execution_id=_required_string(payload, "source_execution_id"),
            replay_manifest_hash=_required_string(payload, "replay_manifest_hash"),
            capability=ExecutionReplayCapability.from_payload(capability),
            planned_calls=tuple(
                ReplayToolCall.from_payload(item)
                for item in _mapping_tuple(payload, "planned_calls")
            ),
            evidence_bindings=tuple(
                ReplayEvidenceBinding.from_payload(item)
                for item in _mapping_tuple(payload, "evidence_bindings")
            ),
            canonicalization_version=_required_string(
                payload, "canonicalization_version"
            ),
            plan_digest=_required_string(payload, "plan_digest"),
            schema_version=_required_string(payload, "schema_version"),
        )


@dataclass(frozen=True)
class ReplayDivergence:
    """A safe description of a tool or tool-free path difference."""

    code: str
    kind: ReplayDivergenceKind | str
    blocking: bool
    attempted_call_id: str | None = None
    scope_id: str | None = None
    safe_diagnostics: Mapping[str, str | int | bool] = field(default_factory=dict)
    schema_version: str = REPLAY_DIVERGENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPLAY_DIVERGENCE_SCHEMA_VERSION:
            raise ValueError("Unsupported replay divergence schema.")
        _require_short_identifier("divergence code", self.code)
        kind = ReplayDivergenceKind(self.kind)
        if not isinstance(self.blocking, bool):
            raise TypeError("divergence blocking must be boolean.")
        if self.attempted_call_id is not None:
            _require_identifier("attempted_call_id", self.attempted_call_id)
        if self.scope_id is not None:
            _require_identifier("scope_id", self.scope_id)
        if kind is ReplayDivergenceKind.TOOL_CALL and self.attempted_call_id is None:
            raise ValueError("Tool-call divergence requires attempted_call_id.")
        if kind is ReplayDivergenceKind.TOOL_FREE_BRANCH and self.scope_id is None:
            raise ValueError("Tool-free branch divergence requires scope_id.")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(
            self, "safe_diagnostics", _safe_diagnostics(self.safe_diagnostics)
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "code": self.code,
            "kind": self.kind.value,
            "blocking": self.blocking,
            "attempted_call_id": self.attempted_call_id,
            "scope_id": self.scope_id,
            "safe_diagnostics": dict(self.safe_diagnostics),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayDivergence:
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "code",
                "kind",
                "blocking",
                "attempted_call_id",
                "scope_id",
                "safe_diagnostics",
            },
            "Replay divergence",
        )
        diagnostics = payload.get("safe_diagnostics")
        if not isinstance(diagnostics, Mapping):
            raise TypeError("Replay divergence safe_diagnostics must be a mapping.")
        return cls(
            code=_required_string(payload, "code"),
            kind=_required_string(payload, "kind"),
            blocking=_required_bool(payload, "blocking"),
            attempted_call_id=_optional_string(payload.get("attempted_call_id")),
            scope_id=_optional_string(payload.get("scope_id")),
            safe_diagnostics=diagnostics,
            schema_version=_required_string(payload, "schema_version"),
        )


@dataclass(frozen=True)
class ReplayToolResolution:
    """Bounded outcome for a single intercepted attempted call."""

    attempted_call_id: str
    outcome: ReplayResolutionOutcome | str
    reason_code: str
    planned_call_id: str | None = None
    selected_evidence_reference: str | None = None
    selected_response_digest: str | None = None
    divergence: ReplayDivergence | None = None
    schema_version: str = REPLAY_TOOL_RESOLUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPLAY_TOOL_RESOLUTION_SCHEMA_VERSION:
            raise ValueError("Unsupported replay tool-resolution schema.")
        _require_identifier("attempted_call_id", self.attempted_call_id)
        outcome = ReplayResolutionOutcome(self.outcome)
        _require_short_identifier("resolution reason_code", self.reason_code)
        if self.planned_call_id is not None:
            _require_identifier("planned_call_id", self.planned_call_id)
        resolved = outcome in {
            ReplayResolutionOutcome.RESOLVED_RECORDED,
            ReplayResolutionOutcome.RESOLVED_INTERVENTION,
        }
        evidence = (self.selected_evidence_reference, self.selected_response_digest)
        if resolved:
            if self.planned_call_id is None:
                raise ValueError("Resolved tool call requires planned_call_id.")
            _require_bounded_reference("selected_evidence_reference", evidence[0])
            _require_sha256("selected_response_digest", evidence[1])
            if self.divergence is not None:
                raise ValueError("Resolved tool call cannot carry a divergence.")
        elif any(value is not None for value in evidence):
            raise ValueError("Unresolved tool call cannot select private evidence.")
        if outcome is ReplayResolutionOutcome.DIVERGED:
            if not isinstance(self.divergence, ReplayDivergence):
                raise ValueError("Diverged tool call requires a ReplayDivergence.")
            if self.divergence.attempted_call_id != self.attempted_call_id:
                raise ValueError(
                    "Divergence attempted call does not match its resolution."
                )
        elif self.divergence is not None:
            raise ValueError("Only diverged tool calls can carry a divergence.")
        object.__setattr__(self, "outcome", outcome)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "attempted_call_id": self.attempted_call_id,
            "outcome": self.outcome.value,
            "reason_code": self.reason_code,
            "planned_call_id": self.planned_call_id,
            "selected_evidence_reference": self.selected_evidence_reference,
            "selected_response_digest": self.selected_response_digest,
            "divergence": self.divergence.to_payload() if self.divergence else None,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayToolResolution:
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "attempted_call_id",
                "outcome",
                "reason_code",
                "planned_call_id",
                "selected_evidence_reference",
                "selected_response_digest",
                "divergence",
            },
            "Replay tool resolution",
        )
        divergence = payload.get("divergence")
        if divergence is not None and not isinstance(divergence, Mapping):
            raise TypeError("Replay resolution divergence must be a mapping.")
        return cls(
            attempted_call_id=_required_string(payload, "attempted_call_id"),
            outcome=_required_string(payload, "outcome"),
            reason_code=_required_string(payload, "reason_code"),
            planned_call_id=_optional_string(payload.get("planned_call_id")),
            selected_evidence_reference=_optional_string(
                payload.get("selected_evidence_reference")
            ),
            selected_response_digest=_optional_string(
                payload.get("selected_response_digest")
            ),
            divergence=ReplayDivergence.from_payload(divergence)
            if isinstance(divergence, Mapping)
            else None,
            schema_version=_required_string(payload, "schema_version"),
        )


@dataclass(frozen=True)
class ReplayExecutionTrace:
    """Bounded logical execution evidence; it deliberately excludes timing."""

    attempted_calls: tuple[ReplayToolCall, ...]
    resolutions: tuple[ReplayToolResolution, ...]
    branch_observations: tuple[ReplayDivergence, ...] = ()
    complete: bool = False
    private_full_trace_reference: str | None = None
    private_full_trace_digest: str | None = None
    trace_digest: str = ""
    schema_version: str = REPLAY_EXECUTION_TRACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPLAY_EXECUTION_TRACE_SCHEMA_VERSION:
            raise ValueError("Unsupported replay execution-trace schema.")
        calls = tuple(sorted(self.attempted_calls, key=lambda call: call.call_id))
        if len(calls) > MAX_TRACE_CALLS or not all(
            isinstance(call, ReplayToolCall) for call in calls
        ):
            raise ValueError(
                f"Trace attempted calls must contain at most {MAX_TRACE_CALLS} calls."
            )
        if any(call.kind is not ReplayToolCallKind.ATTEMPTED for call in calls):
            raise ValueError("Replay execution trace can contain only attempted calls.")
        call_ids = [call.call_id for call in calls]
        if len(set(call_ids)) != len(call_ids):
            raise ValueError("Trace attempted call identities must be unique.")
        known_call_ids = set(call_ids)
        if any(
            not set(call.dependency_call_ids).issubset(known_call_ids) for call in calls
        ):
            raise ValueError("Trace dependency references an unknown attempted call.")
        _validate_acyclic_dependencies(calls)
        resolutions = tuple(
            sorted(self.resolutions, key=lambda item: item.attempted_call_id)
        )
        if not all(isinstance(item, ReplayToolResolution) for item in resolutions):
            raise TypeError(
                "Trace resolutions must contain ReplayToolResolution values."
            )
        resolution_ids = [item.attempted_call_id for item in resolutions]
        if len(set(resolution_ids)) != len(resolution_ids):
            raise ValueError(
                "Trace resolutions must have unique attempted-call identities."
            )
        if not set(resolution_ids).issubset(known_call_ids):
            raise ValueError("Trace resolution references an unknown attempted call.")
        branches = tuple(self.branch_observations)
        if len(branches) > MAX_DIVERGENCES or not all(
            isinstance(item, ReplayDivergence) for item in branches
        ):
            raise ValueError("Trace branch observations are invalid or oversized.")
        if any(
            item.kind is not ReplayDivergenceKind.TOOL_FREE_BRANCH for item in branches
        ):
            raise ValueError(
                "Trace branch observations must be tool-free branch divergences."
            )
        if not isinstance(self.complete, bool):
            raise TypeError("Trace complete must be boolean.")
        if self.complete and set(resolution_ids) != set(call_ids):
            raise ValueError(
                "A complete trace requires one resolution per attempted call."
            )
        references = (self.private_full_trace_reference, self.private_full_trace_digest)
        if any(value is not None for value in references):
            _require_bounded_reference("private_full_trace_reference", references[0])
            _require_sha256("private_full_trace_digest", references[1])
        payload = self._payload_without_digest(calls, resolutions, branches)
        digest = _payload_digest(payload)
        if self.trace_digest and self.trace_digest != digest:
            raise ValueError(
                "Replay execution trace digest does not match its content."
            )
        object.__setattr__(self, "attempted_calls", calls)
        object.__setattr__(self, "resolutions", resolutions)
        object.__setattr__(self, "branch_observations", branches)
        object.__setattr__(self, "trace_digest", digest)

    def _payload_without_digest(
        self,
        calls: tuple[ReplayToolCall, ...] | None = None,
        resolutions: tuple[ReplayToolResolution, ...] | None = None,
        branches: tuple[ReplayDivergence, ...] | None = None,
    ) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "attempted_calls": [
                call.to_payload() for call in (calls or self.attempted_calls)
            ],
            "resolutions": [
                item.to_payload() for item in (resolutions or self.resolutions)
            ],
            "branch_observations": [
                item.to_payload() for item in (branches or self.branch_observations)
            ],
            "complete": self.complete,
            "private_full_trace_reference": self.private_full_trace_reference,
            "private_full_trace_digest": self.private_full_trace_digest,
        }

    def to_payload(self) -> dict[str, object]:
        return {**self._payload_without_digest(), "trace_digest": self.trace_digest}

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayExecutionTrace:
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "attempted_calls",
                "resolutions",
                "branch_observations",
                "complete",
                "private_full_trace_reference",
                "private_full_trace_digest",
                "trace_digest",
            },
            "Replay execution trace",
        )
        return cls(
            attempted_calls=tuple(
                ReplayToolCall.from_payload(item)
                for item in _mapping_tuple(payload, "attempted_calls")
            ),
            resolutions=tuple(
                ReplayToolResolution.from_payload(item)
                for item in _mapping_tuple(payload, "resolutions")
            ),
            branch_observations=tuple(
                ReplayDivergence.from_payload(item)
                for item in _mapping_tuple(payload, "branch_observations")
            ),
            complete=_required_bool(payload, "complete"),
            private_full_trace_reference=_optional_string(
                payload.get("private_full_trace_reference")
            ),
            private_full_trace_digest=_optional_string(
                payload.get("private_full_trace_digest")
            ),
            trace_digest=_required_string(payload, "trace_digest"),
            schema_version=_required_string(payload, "schema_version"),
        )


@dataclass(frozen=True)
class ReplayToolBoundaryCoverage:
    """Declared and observed adapter coverage, without a sandbox claim."""

    declared_tool_boundaries: tuple[str, ...]
    exercised_tool_boundaries: tuple[str, ...]
    unsupported_execution_surfaces: tuple[str, ...]
    execution_path_coverage: ReplayExecutionPathCoverage | str

    def __post_init__(self) -> None:
        declared = _unique_bounded_identifiers(
            "declared_tool_boundaries",
            self.declared_tool_boundaries,
            MAX_BOUNDARIES,
            minimum=1,
        )
        exercised = _unique_bounded_identifiers(
            "exercised_tool_boundaries", self.exercised_tool_boundaries, MAX_BOUNDARIES
        )
        unsupported = _unique_bounded_identifiers(
            "unsupported_execution_surfaces",
            self.unsupported_execution_surfaces,
            MAX_BOUNDARIES,
        )
        if not set(exercised).issubset(set(declared)):
            raise ValueError("Exercised boundaries must be declared.")
        coverage = ReplayExecutionPathCoverage(self.execution_path_coverage)
        if (
            coverage is ReplayExecutionPathCoverage.COMPLETE_DECLARED_BOUNDARIES
            and unsupported
        ):
            raise ValueError("Complete coverage cannot report unsupported surfaces.")
        object.__setattr__(self, "declared_tool_boundaries", declared)
        object.__setattr__(self, "exercised_tool_boundaries", exercised)
        object.__setattr__(self, "unsupported_execution_surfaces", unsupported)
        object.__setattr__(self, "execution_path_coverage", coverage)

    def to_payload(self) -> dict[str, object]:
        return {
            "declared_tool_boundaries": list(self.declared_tool_boundaries),
            "exercised_tool_boundaries": list(self.exercised_tool_boundaries),
            "unsupported_execution_surfaces": list(self.unsupported_execution_surfaces),
            "execution_path_coverage": self.execution_path_coverage.value,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayToolBoundaryCoverage:
        _require_exact_keys(
            payload,
            {
                "declared_tool_boundaries",
                "exercised_tool_boundaries",
                "unsupported_execution_surfaces",
                "execution_path_coverage",
            },
            "Replay tool-boundary coverage",
        )
        return cls(
            declared_tool_boundaries=_string_tuple(payload, "declared_tool_boundaries"),
            exercised_tool_boundaries=_string_tuple(
                payload, "exercised_tool_boundaries"
            ),
            unsupported_execution_surfaces=_string_tuple(
                payload, "unsupported_execution_surfaces"
            ),
            execution_path_coverage=_required_string(
                payload, "execution_path_coverage"
            ),
        )


@dataclass(frozen=True)
class ReplayExecutionAttestation:
    """Bounded adapter report for later worker-side validation.

    It reports cooperative runtime facts.  It cannot prove the absence of
    arbitrary external effects or sandbox an application's code.
    """

    replay_manifest_hash: str
    resolution_plan_digest: str
    phase1_safety_schema_version: str
    phase1_safety_digest: str
    execution_trace_digest: str
    tool_boundary_coverage: ReplayToolBoundaryCoverage
    complete: bool
    resolved_call_count: int
    unresolved_call_count: int
    blocking_divergence_count: int
    non_blocking_divergence_count: int
    intervention_digest: str | None = None
    schema_version: str = REPLAY_EXECUTION_ATTESTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPLAY_EXECUTION_ATTESTATION_SCHEMA_VERSION:
            raise ValueError("Unsupported replay execution-attestation schema.")
        _require_manifest_hash("replay_manifest_hash", self.replay_manifest_hash)
        _require_manifest_hash("resolution_plan_digest", self.resolution_plan_digest)
        if (
            self.phase1_safety_schema_version
            != EVIDENCE_ONLY_REPLAY_SAFETY_SCHEMA_VERSION
        ):
            raise ValueError("Unsupported Phase 1 replay-safety schema version.")
        _require_sha256("phase1_safety_digest", self.phase1_safety_digest)
        _require_manifest_hash("execution_trace_digest", self.execution_trace_digest)
        if self.intervention_digest is not None:
            _require_sha256("intervention_digest", self.intervention_digest)
        if not isinstance(self.tool_boundary_coverage, ReplayToolBoundaryCoverage):
            raise TypeError(
                "tool_boundary_coverage must be ReplayToolBoundaryCoverage."
            )
        if not isinstance(self.complete, bool):
            raise TypeError("attestation complete must be boolean.")
        for name, value in (
            ("resolved_call_count", self.resolved_call_count),
            ("unresolved_call_count", self.unresolved_call_count),
            ("blocking_divergence_count", self.blocking_divergence_count),
            ("non_blocking_divergence_count", self.non_blocking_divergence_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")
        if self.complete and (
            self.unresolved_call_count
            or self.blocking_divergence_count
            or self.tool_boundary_coverage.execution_path_coverage
            is not ReplayExecutionPathCoverage.COMPLETE_DECLARED_BOUNDARIES
        ):
            raise ValueError(
                "A complete attestation cannot report unresolved coverage."
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "replay_manifest_hash": self.replay_manifest_hash,
            "resolution_plan_digest": self.resolution_plan_digest,
            "intervention_digest": self.intervention_digest,
            "phase1_safety_schema_version": self.phase1_safety_schema_version,
            "phase1_safety_digest": self.phase1_safety_digest,
            "execution_trace_digest": self.execution_trace_digest,
            "tool_boundary_coverage": self.tool_boundary_coverage.to_payload(),
            "complete": self.complete,
            "resolved_call_count": self.resolved_call_count,
            "unresolved_call_count": self.unresolved_call_count,
            "blocking_divergence_count": self.blocking_divergence_count,
            "non_blocking_divergence_count": self.non_blocking_divergence_count,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayExecutionAttestation:
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "replay_manifest_hash",
                "resolution_plan_digest",
                "intervention_digest",
                "phase1_safety_schema_version",
                "phase1_safety_digest",
                "execution_trace_digest",
                "tool_boundary_coverage",
                "complete",
                "resolved_call_count",
                "unresolved_call_count",
                "blocking_divergence_count",
                "non_blocking_divergence_count",
            },
            "Replay execution attestation",
        )
        coverage = payload.get("tool_boundary_coverage")
        if not isinstance(coverage, Mapping):
            raise TypeError("Attestation tool_boundary_coverage must be a mapping.")
        return cls(
            replay_manifest_hash=_required_string(payload, "replay_manifest_hash"),
            resolution_plan_digest=_required_string(payload, "resolution_plan_digest"),
            intervention_digest=_optional_string(payload.get("intervention_digest")),
            phase1_safety_schema_version=_required_string(
                payload, "phase1_safety_schema_version"
            ),
            phase1_safety_digest=_required_string(payload, "phase1_safety_digest"),
            execution_trace_digest=_required_string(payload, "execution_trace_digest"),
            tool_boundary_coverage=ReplayToolBoundaryCoverage.from_payload(coverage),
            complete=_required_bool(payload, "complete"),
            resolved_call_count=_required_int(payload, "resolved_call_count"),
            unresolved_call_count=_required_int(payload, "unresolved_call_count"),
            blocking_divergence_count=_required_int(
                payload, "blocking_divergence_count"
            ),
            non_blocking_divergence_count=_required_int(
                payload, "non_blocking_divergence_count"
            ),
            schema_version=_required_string(payload, "schema_version"),
        )


def _validate_acyclic_dependencies(calls: Sequence[ReplayToolCall]) -> None:
    by_id = {call.call_id: call for call in calls}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(call_id: str) -> None:
        if call_id in visiting:
            raise ValueError("Plan dependency graph contains a cycle.")
        if call_id in visited:
            return
        visiting.add(call_id)
        for dependency in by_id[call_id].dependency_call_ids:
            visit(dependency)
        visiting.remove(call_id)
        visited.add(call_id)

    for call in calls:
        visit(call.call_id)


def _payload_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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


def _required_bool(payload: Mapping[str, object], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be boolean.")
    return value


def _required_int(payload: Mapping[str, object], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    return value


def _string_tuple(payload: Mapping[str, object], name: str) -> tuple[str, ...]:
    raw = payload.get(name)
    if not isinstance(raw, (list, tuple)) or not all(
        isinstance(item, str) for item in raw
    ):
        raise TypeError(f"{name} must be a list of strings.")
    return tuple(raw)


def _mapping_tuple(
    payload: Mapping[str, object], name: str
) -> tuple[Mapping[str, object], ...]:
    raw = payload.get(name)
    if not isinstance(raw, (list, tuple)) or not all(
        isinstance(item, Mapping) for item in raw
    ):
        raise TypeError(f"{name} must be a list of mappings.")
    return tuple(raw)


def _require_identifier(name: str, value: object) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier.")


def _require_short_identifier(name: str, value: object) -> None:
    if not isinstance(value, str) or not _SHORT_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier.")


def _require_bounded_reference(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError(f"{name} must be a bounded non-blank reference.")


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a sha256 digest.")


def _require_manifest_hash(name: str, value: object) -> None:
    if not isinstance(value, str) or not _MANIFEST_HASH.fullmatch(value):
        raise ValueError(f"{name} must be a SHA-256 hex digest.")


def _unique_bounded_identifiers(
    name: str, values: Sequence[str], maximum: int, *, minimum: int = 0
) -> tuple[str, ...]:
    items = tuple(values)
    if len(items) < minimum or len(items) > maximum:
        raise ValueError(f"{name} must contain between {minimum} and {maximum} values.")
    for value in items:
        _require_identifier(name, value)
    if len(set(items)) != len(items):
        raise ValueError(f"{name} values must be unique.")
    return tuple(sorted(items))


def _safe_diagnostics(
    value: Mapping[str, str | int | bool],
) -> Mapping[str, str | int | bool]:
    if not isinstance(value, Mapping) or len(value) > MAX_SAFE_DIAGNOSTICS:
        raise ValueError("safe_diagnostics must be a bounded mapping.")
    validated: dict[str, str | int | bool] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not _SAFE_METADATA_KEY.fullmatch(key):
            raise ValueError("safe_diagnostics keys must be safe identifiers.")
        if key.lower() in _SENSITIVE_NAMES:
            raise ValueError(
                "safe_diagnostics cannot contain raw sensitive payload fields."
            )
        if isinstance(item, (bool, int)) or isinstance(item, str) and len(item) <= 128:
            validated[key] = item
        else:
            raise ValueError("safe_diagnostics values must be bounded scalar values.")
    return MappingProxyType(dict(sorted(validated.items())))
