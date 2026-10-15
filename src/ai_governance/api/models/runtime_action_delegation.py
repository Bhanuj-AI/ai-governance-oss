"""REST models for issuer-authorized runtime action delegations."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_governance.runtime_authorization.delegation import (
    RUNTIME_ACTION_DELEGATION_SCHEMA_VERSION,
    RuntimeActionDelegationPermission,
)
from ai_governance.services.runtime_action_delegation_service import (
    RuntimeActionDelegationRegistration,
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class RuntimeActionDelegationPermissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=128)
    resource_type: str = Field(min_length=1, max_length=128)
    resource_references: list[str] = Field(min_length=1, max_length=128)

    @field_validator("action_id", "resource_type")
    @classmethod
    def identifiers_must_be_bounded(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("delegation identifiers must be bounded identifiers.")
        return value

    @field_validator("resource_references")
    @classmethod
    def references_must_be_explicit(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 512 for item in value):
            raise ValueError("resource references must be explicit bounded values.")
        if len(set(value)) != len(value):
            raise ValueError("resource references must be unique.")
        return value

    def to_domain(self) -> RuntimeActionDelegationPermission:
        return RuntimeActionDelegationPermission(
            action_id=self.action_id,
            resource_type=self.resource_type,
            resource_references=tuple(self.resource_references),
        )


class RuntimeActionDelegationRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = RUNTIME_ACTION_DELEGATION_SCHEMA_VERSION
    execution_id: str = Field(min_length=1, max_length=128)
    runtime_actor_id: str = Field(min_length=1, max_length=128)
    permissions: list[RuntimeActionDelegationPermissionRequest] = Field(min_length=1)
    expires_at: datetime
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("schema_version")
    @classmethod
    def schema_version_must_match(cls, value: str) -> str:
        if value != RUNTIME_ACTION_DELEGATION_SCHEMA_VERSION:
            raise ValueError("Unsupported runtime action delegation schema version.")
        return value

    @field_validator("execution_id", "runtime_actor_id", "idempotency_key")
    @classmethod
    def identifiers_must_be_bounded(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("delegation identifiers must be bounded identifiers.")
        return value

    def to_service(self) -> RuntimeActionDelegationRegistration:
        return RuntimeActionDelegationRegistration(
            execution_id=self.execution_id,
            runtime_actor_id=self.runtime_actor_id,
            permissions=tuple(item.to_domain() for item in self.permissions),
            expires_at=self.expires_at,
            idempotency_key=self.idempotency_key,
        )


class RuntimeActionDelegationRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revocation_reference: str | None = Field(
        default=None, min_length=1, max_length=256
    )


class RuntimeActionDelegationPermissionResponse(BaseModel):
    action_id: str
    resource_type: str
    resource_references: list[str]


class RuntimeActionDelegationResponse(BaseModel):
    schema_version: str
    delegation_id: str
    version: str
    execution_id: str
    issuer_id: str
    runtime_actor_id: str
    permissions: list[RuntimeActionDelegationPermissionResponse]
    issued_at: datetime
    expires_at: datetime
    contract_digest: str
    status: str
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    revocation_reference: str | None = None
