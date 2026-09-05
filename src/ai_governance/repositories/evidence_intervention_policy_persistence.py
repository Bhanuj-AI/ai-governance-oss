"""Stable, reference-only persistence for intervention policy versions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ai_governance.domain.causal_audit import (
    EvidenceInterventionPolicy,
    EvidenceInterventionPolicyStatus,
)
from ai_governance.domain.replay import ControlledEvidenceStrategy


def policy_to_payload(policy: EvidenceInterventionPolicy) -> dict[str, Any]:
    return {
        "policy_id": policy.policy_id,
        "version": policy.version,
        "organization_id": policy.organization_id,
        "project_id": policy.project_id,
        "status": policy.status.value,
        "tool_name": policy.tool_name,
        "schema_id": policy.schema_id,
        "schema_version": policy.schema_version,
        "provider_id": policy.provider_id,
        "provider_version": policy.provider_version,
        "allowed_strategies": [item.value for item in policy.allowed_strategies],
        "strategy_configuration": dict(policy.strategy_configuration),
        "created_at": policy.created_at.isoformat(),
        "created_by": policy.created_by,
        "activated_at": policy.activated_at.isoformat()
        if policy.activated_at
        else None,
        "activated_by": policy.activated_by,
        "retired_at": policy.retired_at.isoformat() if policy.retired_at else None,
        "policy_digest": policy.policy_digest,
    }


def policy_from_payload(payload: Mapping[str, Any]) -> EvidenceInterventionPolicy:
    return EvidenceInterventionPolicy(
        policy_id=str(payload["policy_id"]),
        version=int(payload["version"]),
        organization_id=str(payload["organization_id"]),
        project_id=payload.get("project_id"),
        status=EvidenceInterventionPolicyStatus(payload["status"]),
        tool_name=str(payload["tool_name"]),
        schema_id=str(payload["schema_id"]),
        schema_version=str(payload["schema_version"]),
        provider_id=str(payload["provider_id"]),
        provider_version=str(payload["provider_version"]),
        allowed_strategies=tuple(
            ControlledEvidenceStrategy(item) for item in payload["allowed_strategies"]
        ),
        strategy_configuration=payload["strategy_configuration"],
        created_at=datetime.fromisoformat(str(payload["created_at"])),
        created_by=str(payload["created_by"]),
        activated_at=(
            datetime.fromisoformat(str(payload["activated_at"]))
            if payload.get("activated_at")
            else None
        ),
        activated_by=payload.get("activated_by"),
        retired_at=(
            datetime.fromisoformat(str(payload["retired_at"]))
            if payload.get("retired_at")
            else None
        ),
        policy_digest=str(payload["policy_digest"]),
    )
