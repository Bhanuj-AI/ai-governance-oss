"""Versioned, operator-governed counterfactual evidence intervention contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
from typing import Any

from ai_governance.domain.replay import ControlledEvidenceStrategy


class EvidenceInterventionPolicyStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class ToolEvidenceDescriptor:
    """Reference-only contract for evidence eligible for an intervention."""

    tool_call_id: str
    tool_name: str
    evidence_ref: str
    evidence_digest: str
    content_type: str
    schema_id: str
    schema_version: str
    replay_adapter_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("tool_call_id", self.tool_call_id),
            ("tool_name", self.tool_name),
            ("evidence_ref", self.evidence_ref),
            ("evidence_digest", self.evidence_digest),
            ("content_type", self.content_type),
            ("schema_id", self.schema_id),
            ("schema_version", self.schema_version),
            ("replay_adapter_id", self.replay_adapter_id),
        ):
            if not value.strip():
                raise ValueError(f"Tool evidence descriptor {name} is required.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class EvidenceInterventionPolicy:
    """An immutable policy version once activated; raw evidence is never stored."""

    policy_id: str
    version: int
    organization_id: str
    project_id: str | None
    status: EvidenceInterventionPolicyStatus
    tool_name: str
    schema_id: str
    schema_version: str
    provider_id: str
    provider_version: str
    allowed_strategies: tuple[ControlledEvidenceStrategy, ...]
    strategy_configuration: Mapping[str, Any]
    created_at: datetime
    created_by: str
    activated_at: datetime | None = None
    activated_by: str | None = None
    retired_at: datetime | None = None
    policy_digest: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("policy_id", self.policy_id),
            ("organization_id", self.organization_id),
            ("tool_name", self.tool_name),
            ("schema_id", self.schema_id),
            ("schema_version", self.schema_version),
            ("provider_id", self.provider_id),
            ("provider_version", self.provider_version),
            ("created_by", self.created_by),
        ):
            if not value.strip():
                raise ValueError(f"Intervention policy {name} is required.")
        if self.project_id is not None and not self.project_id.strip():
            raise ValueError("Intervention policy project_id must not be blank.")
        if self.version < 1 or not self.allowed_strategies:
            raise ValueError("Intervention policy version and strategies are required.")
        if len(set(self.allowed_strategies)) != len(self.allowed_strategies):
            raise ValueError("Intervention policy strategies must be unique.")
        if self.status is EvidenceInterventionPolicyStatus.ACTIVE and (
            self.activated_at is None or not self.activated_by
        ):
            raise ValueError(
                "Active intervention policies require activation evidence."
            )
        if (
            self.status is EvidenceInterventionPolicyStatus.RETIRED
            and self.retired_at is None
        ):
            raise ValueError("Retired intervention policies require retired_at.")
        configuration = MappingProxyType(dict(self.strategy_configuration))
        object.__setattr__(self, "strategy_configuration", configuration)
        expected_digest = _digest(self, configuration)
        if self.policy_digest and self.policy_digest != expected_digest:
            raise ValueError(
                "Intervention policy digest does not match its immutable content."
            )
        object.__setattr__(self, "policy_digest", expected_digest)

    def activate(self, actor_id: str, now: datetime) -> EvidenceInterventionPolicy:
        if self.status is EvidenceInterventionPolicyStatus.ACTIVE:
            return self
        if self.status is not EvidenceInterventionPolicyStatus.DRAFT:
            raise ValueError("Only draft intervention policies can be activated.")
        if not actor_id.strip():
            raise ValueError("Policy activation requires an actor.")
        return replace(
            self,
            status=EvidenceInterventionPolicyStatus.ACTIVE,
            activated_at=now,
            activated_by=actor_id,
        )

    def retire(self, now: datetime) -> EvidenceInterventionPolicy:
        if self.status is EvidenceInterventionPolicyStatus.RETIRED:
            return self
        if self.status is not EvidenceInterventionPolicyStatus.ACTIVE:
            raise ValueError("Only active intervention policies can be retired.")
        return replace(
            self, status=EvidenceInterventionPolicyStatus.RETIRED, retired_at=now
        )

    def next_draft(
        self, actor_id: str, now: datetime, configuration: Mapping[str, Any]
    ) -> EvidenceInterventionPolicy:
        if self.status is not EvidenceInterventionPolicyStatus.ACTIVE:
            raise ValueError("Only an active policy can create an edited version.")
        return EvidenceInterventionPolicy(
            policy_id=self.policy_id,
            version=self.version + 1,
            organization_id=self.organization_id,
            project_id=self.project_id,
            status=EvidenceInterventionPolicyStatus.DRAFT,
            tool_name=self.tool_name,
            schema_id=self.schema_id,
            schema_version=self.schema_version,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            allowed_strategies=self.allowed_strategies,
            strategy_configuration=configuration,
            created_at=now,
            created_by=actor_id,
        )


@dataclass(frozen=True)
class CounterfactualEvidence:
    strategy: ControlledEvidenceStrategy
    provider_id: str
    provider_version: str
    policy_id: str
    policy_version: int
    seed: int
    original_evidence_digest: str
    counterfactual_evidence_ref: str
    counterfactual_evidence_digest: str
    schema_valid: bool
    semantic_valid: bool
    generation_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("provider_id", self.provider_id),
            ("provider_version", self.provider_version),
            ("policy_id", self.policy_id),
            ("original_evidence_digest", self.original_evidence_digest),
            ("counterfactual_evidence_ref", self.counterfactual_evidence_ref),
            ("counterfactual_evidence_digest", self.counterfactual_evidence_digest),
        ):
            if not value.strip():
                raise ValueError(f"Counterfactual evidence {name} is required.")
        if self.policy_version < 1 or not self.schema_valid or not self.semantic_valid:
            raise ValueError("Counterfactual evidence must be validated before Replay.")
        if self.original_evidence_digest == self.counterfactual_evidence_digest:
            raise ValueError(
                "Counterfactual evidence must materially differ from original evidence."
            )
        object.__setattr__(
            self,
            "generation_metadata",
            MappingProxyType(dict(self.generation_metadata)),
        )


def _digest(
    policy: EvidenceInterventionPolicy, configuration: Mapping[str, Any]
) -> str:
    payload = {
        "policy_id": policy.policy_id,
        "version": policy.version,
        "organization_id": policy.organization_id,
        "project_id": policy.project_id,
        "tool_name": policy.tool_name,
        "schema_id": policy.schema_id,
        "schema_version": policy.schema_version,
        "provider_id": policy.provider_id,
        "provider_version": policy.provider_version,
        "allowed_strategies": [item.value for item in policy.allowed_strategies],
        "strategy_configuration": dict(configuration),
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
