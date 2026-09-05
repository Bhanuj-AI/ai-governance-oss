"""Runtime finding lifecycle events for the Event Platform.

Published when findings are created, updated, or resolved.
"""

from __future__ import annotations
from types import MappingProxyType

from ai_governance.events.contracts import TransactionalDomainEvent


class RuntimeFindingCreated(TransactionalDomainEvent):
    """Published when a new runtime finding is generated."""

    finding_id: str
    finding_type: str
    subject_type: str
    subject_id: str
    severity: str

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(
            self,
            "payload",
            MappingProxyType({
                **dict(self.payload),
                "finding_id": self.finding_id,
                "finding_type": self.finding_type,
                "subject_type": self.subject_type,
                "subject_id": self.subject_id,
                "severity": self.severity,
            }),
        )


class RuntimeFindingUpdated(TransactionalDomainEvent):
    """Published when an active finding is updated with new metrics."""

    finding_id: str
    finding_type: str
    observation_count: int

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(
            self,
            "payload",
            MappingProxyType({
                **dict(self.payload),
                "finding_id": self.finding_id,
                "finding_type": self.finding_type,
                "observation_count": self.observation_count,
            }),
        )


class RuntimeFindingResolved(TransactionalDomainEvent):
    """Published when a finding is resolved (condition no longer holds)."""

    finding_id: str
    finding_type: str
    subject_type: str
    subject_id: str

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(
            self,
            "payload",
            MappingProxyType({
                **dict(self.payload),
                "finding_id": self.finding_id,
                "finding_type": self.finding_type,
                "subject_type": self.subject_type,
                "subject_id": self.subject_id,
            }),
        )
