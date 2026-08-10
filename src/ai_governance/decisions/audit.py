from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from ai_governance.decisions.validation import (
    copy_mapping,
    require_non_empty,
    require_optional_non_empty,
    require_timezone_aware,
)


class DecisionAuditAction(str, Enum):
    """
    Append-only audit action for governance decisions.
    """

    CREATED = "CREATED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class DecisionAuditRecord:
    """
    Audit record for governance decision lifecycle changes.
    """

    decision_id: str
    action: DecisionAuditAction | str
    producer_id: str
    reason: str
    audit_id: str = field(default_factory=lambda: str(uuid4()))
    actor_id: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("decision audit_id", self.audit_id)
        require_non_empty("decision audit decision_id", self.decision_id)
        require_non_empty("decision audit producer_id", self.producer_id)
        require_non_empty("decision audit reason", self.reason)
        require_optional_non_empty("decision audit actor_id", self.actor_id)
        require_optional_non_empty(
            "decision audit correlation_id",
            self.correlation_id,
        )
        require_optional_non_empty("decision audit request_id", self.request_id)
        require_timezone_aware("decision audit created_at", self.created_at)
        object.__setattr__(
            self,
            "action",
            DecisionAuditAction(self.action),
        )
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))
