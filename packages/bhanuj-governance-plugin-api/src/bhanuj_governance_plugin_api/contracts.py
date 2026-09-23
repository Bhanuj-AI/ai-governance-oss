"""Public plugin contributions with no BHANUJ Core imports."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bhanuj_governance_plugin_api.replay import ReplayExecutionAdapter

_REPLAY_ADAPTER_COMPONENT = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


@dataclass(frozen=True)
class ReplayExecutionAdapterContribution:
    """One versioned external adapter contributed by a runtime plugin."""

    adapter_id: str
    adapter_version: str
    adapter: ReplayExecutionAdapter

    def __post_init__(self) -> None:
        if not _REPLAY_ADAPTER_COMPONENT.fullmatch(
            self.adapter_id
        ) or not _REPLAY_ADAPTER_COMPONENT.fullmatch(self.adapter_version):
            raise ValueError(
                "Replay adapter contribution requires lowercase, hyphen-delimited adapter ID and version."
            )
        if self.adapter.name != self.name:
            raise ValueError(
                "Replay adapter contribution identity must match adapter.name."
            )

    @property
    def name(self) -> str:
        return f"{self.adapter_id}/{self.adapter_version}"
