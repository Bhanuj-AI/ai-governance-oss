"""Explicit replay capability advertised by an observed agent runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ai_governance.domain.replay import ControlledEvidenceStrategy


@dataclass(frozen=True)
class AgentRuntimeReplayCapability:
    """Opaque, versioned reference that permits a runtime-specific replay.

    It intentionally excludes prompts, responses, credentials, tool payloads,
    and executable state. The selected adapter resolves the opaque reference
    only under the original tenant context.
    """

    runtime_type: str
    adapter_id: str
    adapter_version: str
    replay_reference: str
    supported_interventions: tuple[ControlledEvidenceStrategy, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("runtime_type", self.runtime_type),
            ("adapter_id", self.adapter_id),
            ("adapter_version", self.adapter_version),
            ("replay_reference", self.replay_reference),
        ):
            if not value.strip():
                raise ValueError(f"Replay capability {name} is required.")
        if not self.supported_interventions:
            raise ValueError("Replay capability must support an intervention.")
        if len(set(self.supported_interventions)) != len(self.supported_interventions):
            raise ValueError("Replay capability interventions must be unique.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
