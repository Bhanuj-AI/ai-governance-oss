"""Immutable, issuer-authorized delegations for protected runtime actions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .contracts import _require_digest, _require_identifier, _require_non_blank

RUNTIME_ACTION_DELEGATION_SCHEMA_VERSION = "runtime-action-delegation/v1"


class RuntimeActionDelegationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


@dataclass(frozen=True)
class RuntimeActionDelegationPermission:
    """One explicit action and resource scope granted to a runtime actor."""

    action_id: str
    resource_type: str
    resource_references: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_identifier("action_id", self.action_id)
        _require_identifier("resource_type", self.resource_type)
        if not self.resource_references:
            raise ValueError(
                "resource_references must contain an explicit resource scope."
            )
        if len(set(self.resource_references)) != len(self.resource_references):
            raise ValueError("resource_references must be unique.")
        for reference in self.resource_references:
            _require_non_blank("resource_reference", reference)
            if len(reference) > 512:
                raise ValueError("resource_reference must not exceed 512 characters.")


@dataclass(frozen=True)
class RuntimeActionDelegation:
    """Versioned immutable grant, except for its one-way revocation state."""

    delegation_id: str
    version: str
    organization_id: str
    project_id: str
    execution_id: str
    issuer_id: str
    runtime_actor_id: str
    permissions: tuple[RuntimeActionDelegationPermission, ...]
    issued_at: datetime
    expires_at: datetime
    contract_digest: str
    idempotency_key: str
    status: RuntimeActionDelegationStatus | str = RuntimeActionDelegationStatus.ACTIVE
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    revocation_reference: str | None = None
    schema_version: str = RUNTIME_ACTION_DELEGATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_ACTION_DELEGATION_SCHEMA_VERSION:
            raise ValueError("Unsupported runtime action delegation schema version.")
        for name, value in (
            ("delegation_id", self.delegation_id),
            ("version", self.version),
            ("organization_id", self.organization_id),
            ("project_id", self.project_id),
            ("execution_id", self.execution_id),
            ("issuer_id", self.issuer_id),
            ("runtime_actor_id", self.runtime_actor_id),
            ("idempotency_key", self.idempotency_key),
        ):
            _require_identifier(name, value)
        if not self.permissions:
            raise ValueError("permissions must not be empty.")
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("delegation timestamps must be timezone-aware.")
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be later than issued_at.")
        _require_digest("contract_digest", self.contract_digest)
        if self.contract_digest != self.compute_contract_digest():
            raise ValueError(
                "contract_digest does not match immutable delegation content."
            )
        status = RuntimeActionDelegationStatus(self.status)
        object.__setattr__(self, "status", status)
        if status is RuntimeActionDelegationStatus.REVOKED:
            if self.revoked_at is None or self.revoked_by is None:
                raise ValueError("revoked delegations require revocation evidence.")
            _require_identifier("revoked_by", self.revoked_by)
            if self.revoked_at.tzinfo is None:
                raise ValueError("revoked_at must be timezone-aware.")
            if self.revocation_reference is not None:
                _require_non_blank("revocation_reference", self.revocation_reference)
                if len(self.revocation_reference) > 256:
                    raise ValueError(
                        "revocation_reference must not exceed 256 characters."
                    )
        elif any(
            value is not None
            for value in (self.revoked_at, self.revoked_by, self.revocation_reference)
        ):
            raise ValueError("active delegations cannot carry revocation evidence.")

    def compute_contract_digest(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "delegation_id": self.delegation_id,
            "version": self.version,
            "organization_id": self.organization_id,
            "project_id": self.project_id,
            "execution_id": self.execution_id,
            "issuer_id": self.issuer_id,
            "runtime_actor_id": self.runtime_actor_id,
            "permissions": [
                {
                    "action_id": permission.action_id,
                    "resource_type": permission.resource_type,
                    "resource_references": list(permission.resource_references),
                }
                for permission in self.permissions
            ],
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "idempotency_key": self.idempotency_key,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"

    def permits(
        self,
        *,
        actor_id: str,
        execution_id: str,
        action_id: str,
        resource_type: str,
        resource_reference: str,
        now: datetime,
    ) -> bool:
        if (
            self.status is not RuntimeActionDelegationStatus.ACTIVE
            or self.expires_at <= now
            or self.runtime_actor_id != actor_id
            or self.execution_id != execution_id
        ):
            return False
        return any(
            permission.action_id == action_id
            and permission.resource_type == resource_type
            and resource_reference in permission.resource_references
            for permission in self.permissions
        )


def create_runtime_action_delegation(
    *,
    delegation_id: str,
    organization_id: str,
    project_id: str,
    execution_id: str,
    issuer_id: str,
    runtime_actor_id: str,
    permissions: Sequence[RuntimeActionDelegationPermission],
    issued_at: datetime,
    expires_at: datetime,
    idempotency_key: str,
    version: str = "1",
) -> RuntimeActionDelegation:
    """Construct a delegation and bind a digest to its immutable content."""

    payload = {
        "schema_version": RUNTIME_ACTION_DELEGATION_SCHEMA_VERSION,
        "delegation_id": delegation_id,
        "version": version,
        "organization_id": organization_id,
        "project_id": project_id,
        "execution_id": execution_id,
        "issuer_id": issuer_id,
        "runtime_actor_id": runtime_actor_id,
        "permissions": [
            {
                "action_id": permission.action_id,
                "resource_type": permission.resource_type,
                "resource_references": list(permission.resource_references),
            }
            for permission in permissions
        ],
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "idempotency_key": idempotency_key,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"
    return RuntimeActionDelegation(
        delegation_id=delegation_id,
        version=version,
        organization_id=organization_id,
        project_id=project_id,
        execution_id=execution_id,
        issuer_id=issuer_id,
        runtime_actor_id=runtime_actor_id,
        permissions=tuple(permissions),
        issued_at=issued_at,
        expires_at=expires_at,
        contract_digest=digest,
        idempotency_key=idempotency_key,
    )
