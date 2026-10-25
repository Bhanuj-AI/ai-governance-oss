"""Versioned evidence manifest for deciding whether an execution is replayable."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Any

REPLAY_MANIFEST_SCHEMA_VERSION = "replay-manifest/v1"


class ReplayManifestEligibility(str, Enum):
    """Whether captured evidence is sufficient for a safe replay attempt."""

    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class ReplayManifestReasonCode(str, Enum):
    """Stable, privacy-bounded reasons why a manifest is ineligible."""

    EXECUTION_NOT_TERMINAL = "EXECUTION_NOT_TERMINAL"
    MISSING_REPLAY_CAPABILITY = "MISSING_REPLAY_CAPABILITY"
    INVALID_REPLAY_CAPABILITY = "INVALID_REPLAY_CAPABILITY"
    MISSING_ISOLATION_GUARANTEE = "MISSING_ISOLATION_GUARANTEE"
    TOOL_CALL_IDENTITY_MISSING = "TOOL_CALL_IDENTITY_MISSING"
    EVIDENCE_REFERENCE_MISSING = "EVIDENCE_REFERENCE_MISSING"
    TOOL_CALL_GRAPH_INVALID = "TOOL_CALL_GRAPH_INVALID"
    TENANT_SCOPE_MISMATCH = "TENANT_SCOPE_MISMATCH"


@dataclass(frozen=True)
class ReplayManifestReason:
    code: ReplayManifestReasonCode | str
    message: str

    def __post_init__(self) -> None:
        code = ReplayManifestReasonCode(self.code)
        if (
            not isinstance(self.message, str)
            or not self.message.strip()
            or len(self.message) > 512
        ):
            raise ValueError("Replay manifest reason must be bounded and non-blank.")
        object.__setattr__(self, "code", code)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}


@dataclass(frozen=True)
class ReplayManifest:
    """Immutable, reference-only evidence assessment attached to a replay config.

    It records whether the source evidence is sufficient to reproduce an
    execution safely. It does not execute, retry, or prove an external effect.
    """

    source_execution_id: str
    source_execution_status: str
    eligibility: ReplayManifestEligibility | str
    tool_call_count: int
    evidence_reference_count: int
    reasons: tuple[ReplayManifestReason, ...] = ()
    runtime_type: str | None = None
    adapter_id: str | None = None
    adapter_version: str | None = None
    replay_reference: str | None = None
    isolation_guarantee: str | None = None
    schema_version: str = REPLAY_MANIFEST_SCHEMA_VERSION
    manifest_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != REPLAY_MANIFEST_SCHEMA_VERSION:
            raise ValueError("Unsupported replay manifest schema version.")
        for name, value in (
            ("source_execution_id", self.source_execution_id),
            ("source_execution_status", self.source_execution_status),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise ValueError(f"Replay manifest {name} must be bounded and non-blank.")
        if (
            isinstance(self.tool_call_count, bool)
            or isinstance(self.evidence_reference_count, bool)
            or not isinstance(self.tool_call_count, int)
            or not isinstance(self.evidence_reference_count, int)
            or self.tool_call_count < 0
            or self.evidence_reference_count < 0
        ):
            raise ValueError("Replay manifest evidence counts must be non-negative.")
        eligibility = ReplayManifestEligibility(self.eligibility)
        reasons = tuple(self.reasons)
        if not all(isinstance(reason, ReplayManifestReason) for reason in reasons):
            raise TypeError("Replay manifest reasons must be typed reasons.")
        if eligibility is ReplayManifestEligibility.ELIGIBLE and reasons:
            raise ValueError("An eligible replay manifest cannot contain ineligibility reasons.")
        if eligibility is ReplayManifestEligibility.INELIGIBLE and not reasons:
            raise ValueError("An ineligible replay manifest requires an explicit reason.")
        for name, value in (
            ("runtime_type", self.runtime_type),
            ("adapter_id", self.adapter_id),
            ("adapter_version", self.adapter_version),
            ("replay_reference", self.replay_reference),
            ("isolation_guarantee", self.isolation_guarantee),
        ):
            if value is not None and (
                not isinstance(value, str) or not value.strip() or len(value) > 512
            ):
                raise ValueError(f"Replay manifest {name} must be bounded when present.")
        if eligibility is ReplayManifestEligibility.ELIGIBLE and not all(
            (
                self.runtime_type,
                self.adapter_id,
                self.adapter_version,
                self.replay_reference,
                self.isolation_guarantee,
            )
        ):
            raise ValueError(
                "An eligible replay manifest requires capability and isolation evidence."
            )
        payload = self._payload_without_hash(eligibility, reasons)
        digest = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if self.manifest_hash and self.manifest_hash != digest:
            raise ValueError("Replay manifest hash does not match its evidence.")
        object.__setattr__(self, "eligibility", eligibility)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "manifest_hash", digest)

    @property
    def is_eligible(self) -> bool:
        return self.eligibility is ReplayManifestEligibility.ELIGIBLE

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._payload_without_hash(self.eligibility, self.reasons),
            "manifest_hash": self.manifest_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ReplayManifest:
        if not isinstance(value, Mapping):
            raise TypeError("Replay manifest must be a mapping.")
        try:
            reasons = value.get("reasons", ())
            if not isinstance(reasons, (list, tuple)):
                raise TypeError("Replay manifest reasons must be a list.")
            return cls(
                source_execution_id=_required_string(value, "source_execution_id"),
                source_execution_status=_required_string(
                    value, "source_execution_status"
                ),
                eligibility=_required_string(value, "eligibility"),
                tool_call_count=_required_int(value, "tool_call_count"),
                evidence_reference_count=_required_int(
                    value, "evidence_reference_count"
                ),
                reasons=tuple(
                    _reason_from_mapping(reason)
                    for reason in reasons
                ),
                runtime_type=_optional_string(value.get("runtime_type")),
                adapter_id=_optional_string(value.get("adapter_id")),
                adapter_version=_optional_string(value.get("adapter_version")),
                replay_reference=_optional_string(value.get("replay_reference")),
                isolation_guarantee=_optional_string(
                    value.get("isolation_guarantee")
                ),
                schema_version=_required_string(value, "schema_version"),
                manifest_hash=_required_string(value, "manifest_hash"),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Replay manifest is malformed.") from error

    def _payload_without_hash(
        self,
        eligibility: ReplayManifestEligibility,
        reasons: tuple[ReplayManifestReason, ...],
    ) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_execution_id": self.source_execution_id,
            "source_execution_status": self.source_execution_status,
            "eligibility": eligibility.value,
            "tool_call_count": self.tool_call_count,
            "evidence_reference_count": self.evidence_reference_count,
            "reasons": [reason.to_dict() for reason in reasons],
            "runtime_type": self.runtime_type,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "replay_reference": self.replay_reference,
            "isolation_guarantee": self.isolation_guarantee,
        }


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Replay manifest values must be strings when present.")
    return value


def _required_string(value: Mapping[str, Any], field: str) -> str:
    raw = value[field]
    if not isinstance(raw, str):
        raise TypeError(f"Replay manifest {field} must be a string.")
    return raw


def _required_int(value: Mapping[str, Any], field: str) -> int:
    raw = value[field]
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"Replay manifest {field} must be an integer.")
    return raw


def _reason_from_mapping(value: object) -> ReplayManifestReason:
    if not isinstance(value, Mapping):
        raise TypeError("Replay manifest reason must be a mapping.")
    return ReplayManifestReason(
        code=_required_string(value, "code"),
        message=_required_string(value, "message"),
    )
