"""Bounded runtime attestations for evidence-only controlled replay."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

EVIDENCE_ONLY_REPLAY_SAFETY_SCHEMA_VERSION = "evidence-only-replay-safety/v1"
_EVIDENCE_ONLY_REPLAY_CAPABILITY_SCHEMA_VERSION = "evidence-only-replay-capability/v1"


@dataclass(frozen=True)
class EvidenceOnlyReplaySafetyMetadata:
    """Runtime-produced, bounded evidence that a replay honored its contract."""

    schema_version: str
    capability_schema_version: str
    replay_manifest_hash: str
    isolation_guarantee: str
    intervention_digest: str
    runtime_tool_call_id: str
    private_snapshot_integrity_verified: bool
    unobserved_tool_call_count: int
    external_side_effects_performed: bool

    def __post_init__(self) -> None:
        if self.schema_version != EVIDENCE_ONLY_REPLAY_SAFETY_SCHEMA_VERSION:
            raise ValueError("Unsupported evidence-only replay safety schema.")
        if self.capability_schema_version != _EVIDENCE_ONLY_REPLAY_CAPABILITY_SCHEMA_VERSION:
            raise ValueError("Safety metadata names an unsupported capability schema.")
        if not _sha256(self.replay_manifest_hash):
            raise ValueError("Replay safety metadata requires a manifest SHA-256 hash.")
        for name, value, maximum in (
            ("isolation_guarantee", self.isolation_guarantee, 128),
            ("intervention_digest", self.intervention_digest, 64),
            ("runtime_tool_call_id", self.runtime_tool_call_id, 256),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"Replay safety metadata {name} must be bounded.")
        if not self.private_snapshot_integrity_verified:
            raise ValueError("Replay safety metadata requires snapshot integrity verification.")
        if (
            isinstance(self.unobserved_tool_call_count, bool)
            or not isinstance(self.unobserved_tool_call_count, int)
            or self.unobserved_tool_call_count != 0
        ):
            raise ValueError("Evidence-only replay must report zero unobserved tool calls.")
        if self.external_side_effects_performed:
            raise ValueError("Evidence-only replay must report no external side effects.")

    @classmethod
    def from_metadata(cls, value: object) -> EvidenceOnlyReplaySafetyMetadata:
        if not isinstance(value, Mapping):
            raise TypeError("Replay safety metadata must be an object.")
        expected = {
            "schema_version",
            "capability_schema_version",
            "replay_manifest_hash",
            "isolation_guarantee",
            "intervention_digest",
            "runtime_tool_call_id",
            "private_snapshot_integrity_verified",
            "unobserved_tool_call_count",
            "external_side_effects_performed",
        }
        if set(value) != expected:
            raise ValueError("Replay safety metadata has an unsupported shape.")
        return cls(
            schema_version=_string(value, "schema_version"),
            capability_schema_version=_string(value, "capability_schema_version"),
            replay_manifest_hash=_string(value, "replay_manifest_hash"),
            isolation_guarantee=_string(value, "isolation_guarantee"),
            intervention_digest=_string(value, "intervention_digest"),
            runtime_tool_call_id=_string(value, "runtime_tool_call_id"),
            private_snapshot_integrity_verified=_true(
                value, "private_snapshot_integrity_verified"
            ),
            unobserved_tool_call_count=_integer(value, "unobserved_tool_call_count"),
            external_side_effects_performed=_false(
                value, "external_side_effects_performed"
            ),
        )

    def to_metadata(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "capability_schema_version": self.capability_schema_version,
            "replay_manifest_hash": self.replay_manifest_hash,
            "isolation_guarantee": self.isolation_guarantee,
            "intervention_digest": self.intervention_digest,
            "runtime_tool_call_id": self.runtime_tool_call_id,
            "private_snapshot_integrity_verified": self.private_snapshot_integrity_verified,
            "unobserved_tool_call_count": self.unobserved_tool_call_count,
            "external_side_effects_performed": self.external_side_effects_performed,
        }


def _string(value: Mapping[str, object], name: str) -> str:
    raw = value.get(name)
    if not isinstance(raw, str):
        raise TypeError(f"Replay safety metadata {name} must be a string.")
    return raw


def _true(value: Mapping[str, object], name: str) -> bool:
    if value.get(name) is not True:
        raise ValueError(f"Replay safety metadata {name} must be true.")
    return True


def _false(value: Mapping[str, object], name: str) -> bool:
    if value.get(name) is not False:
        raise ValueError(f"Replay safety metadata {name} must be false.")
    return False


def _integer(value: Mapping[str, object], name: str) -> int:
    raw = value.get(name)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"Replay safety metadata {name} must be an integer.")
    return raw


def _sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
