"""Versioned declaration required for execution-faithful controlled replay."""

from __future__ import annotations

from dataclasses import dataclass

EVIDENCE_ONLY_REPLAY_CAPABILITY_SCHEMA_VERSION = "evidence-only-replay-capability/v1"


@dataclass(frozen=True)
class EvidenceOnlyReplayCapability:
    """Runtime promise to resolve replay tool evidence without live fallback.

    This is deliberately separate from ``AgentRuntimeReplayCapability``.  The
    latter identifies a runtime adapter and opaque replay reference; this
    declaration is required before Causal Audit accepts that adapter for an
    execution-faithful controlled replay.
    """

    schema_version: str
    recorded_evidence_only: bool
    unobserved_tool_calls_fail: bool
    external_side_effects_prohibited: bool

    def __post_init__(self) -> None:
        if self.schema_version != EVIDENCE_ONLY_REPLAY_CAPABILITY_SCHEMA_VERSION:
            raise ValueError("Unsupported evidence-only replay capability schema.")
        if not self.recorded_evidence_only:
            raise ValueError("Evidence-only replay must use recorded evidence only.")
        if not self.unobserved_tool_calls_fail:
            raise ValueError("Evidence-only replay must fail on unobserved tool calls.")
        if not self.external_side_effects_prohibited:
            raise ValueError(
                "Evidence-only replay must prohibit external side effects."
            )

    @classmethod
    def from_metadata(cls, value: object) -> EvidenceOnlyReplayCapability:
        if not isinstance(value, dict):
            raise TypeError("Evidence-only replay capability must be an object.")
        return cls(
            schema_version=_required_string(value, "schema_version"),
            recorded_evidence_only=_required_true(value, "recorded_evidence_only"),
            unobserved_tool_calls_fail=_required_true(
                value, "unobserved_tool_calls_fail"
            ),
            external_side_effects_prohibited=_required_true(
                value, "external_side_effects_prohibited"
            ),
        )

    def to_metadata(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "recorded_evidence_only": self.recorded_evidence_only,
            "unobserved_tool_calls_fail": self.unobserved_tool_calls_fail,
            "external_side_effects_prohibited": self.external_side_effects_prohibited,
        }


def _required_string(value: dict[object, object], name: str) -> str:
    raw = value.get(name)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"Evidence-only replay capability {name} is required.")
    return raw


def _required_true(value: dict[object, object], name: str) -> bool:
    if value.get(name) is not True:
        raise ValueError(f"Evidence-only replay capability {name} must be true.")
    return True
