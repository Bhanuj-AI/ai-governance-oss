"""REST transport models for runtime action authorization v2."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_governance.runtime_authorization import (
    RUNTIME_ACTION_AUTHORIZATION_SCHEMA_VERSION,
    RuntimeActionAuthorizationRequest,
    RuntimeActionResource,
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SENSITIVE_CONTEXT_KEYS = frozenset(
    {
        "prompt",
        "system_prompt",
        "response",
        "messages",
        "conversation",
        "reasoning",
        "chain_of_thought",
        "credentials",
        "password",
        "secret",
        "token",
    }
)


class RuntimeActionResourceRequest(BaseModel):
    """Opaque resource reference; never include a tool payload or output."""

    model_config = ConfigDict(extra="forbid")

    resource_type: str = Field(min_length=1, max_length=128)
    resource_reference: str = Field(min_length=1, max_length=512)

    @field_validator("resource_type")
    @classmethod
    def resource_type_must_be_identifier(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("resource_type must be a bounded identifier.")
        return value

    def to_domain(self) -> RuntimeActionResource:
        return RuntimeActionResource(
            resource_type=self.resource_type,
            resource_reference=self.resource_reference,
        )


class RuntimeActionAuthorizationRequestBody(BaseModel):
    """Versioned request for one external runtime operation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["runtime-action-authorization/v2"] = (
        RUNTIME_ACTION_AUTHORIZATION_SCHEMA_VERSION
    )
    execution_id: str = Field(min_length=1, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    action_id: str = Field(min_length=1, max_length=128)
    resource: RuntimeActionResourceRequest
    delegation_id: str | None = Field(default=None, min_length=1, max_length=128)
    delegation_version: str | None = Field(default=None, min_length=1, max_length=128)
    delegation_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    tool_arguments_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    context: dict[str, str | int | float | bool] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=128)
    policy_id: str | None = Field(default=None, min_length=1, max_length=128)
    expected_policy_version: str | None = Field(
        default=None, min_length=1, max_length=128
    )

    @field_validator(
        "execution_id",
        "correlation_id",
        "action_id",
        "idempotency_key",
        "delegation_id",
        "delegation_version",
        "policy_id",
        "expected_policy_version",
    )
    @classmethod
    def identifiers_must_be_bounded(cls, value: str | None) -> str | None:
        if value is not None and not _IDENTIFIER.fullmatch(value):
            raise ValueError("authorization identifiers must be bounded identifiers.")
        return value

    @field_validator("context")
    @classmethod
    def context_must_not_carry_sensitive_content(
        cls, value: dict[str, str | int | float | bool]
    ) -> dict[str, str | int | float | bool]:
        if len(value) > 32:
            raise ValueError("context must not contain more than 32 facts.")
        for key, fact in value.items():
            normalized = key.lower().replace("-", "_").replace(" ", "_")
            if normalized in _SENSITIVE_CONTEXT_KEYS:
                raise ValueError(
                    "context must not contain prompts, credentials, or reasoning."
                )
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key):
                raise ValueError("context fact keys must be bounded identifiers.")
            if isinstance(fact, str) and (not fact.strip() or len(fact) > 256):
                raise ValueError(
                    "context string facts must be non-blank and at most 256 characters."
                )
        return value

    @model_validator(mode="after")
    def expected_version_requires_policy(self) -> RuntimeActionAuthorizationRequestBody:
        if self.expected_policy_version is not None and self.policy_id is None:
            raise ValueError("expected_policy_version requires policy_id.")
        delegation = (
            self.delegation_id,
            self.delegation_version,
            self.delegation_digest,
        )
        if any(value is not None for value in delegation) and any(
            value is None for value in delegation
        ):
            raise ValueError(
                "delegation_id, delegation_version, and delegation_digest are required together."
            )
        return self

    def to_domain(self) -> RuntimeActionAuthorizationRequest:
        return RuntimeActionAuthorizationRequest(
            schema_version=self.schema_version,
            execution_id=self.execution_id,
            correlation_id=self.correlation_id,
            action_id=self.action_id,
            resource=self.resource.to_domain(),
            delegation_id=self.delegation_id,
            delegation_version=self.delegation_version,
            delegation_digest=self.delegation_digest,
            tool_arguments_digest=self.tool_arguments_digest,
            context=self.context,
            idempotency_key=self.idempotency_key,
            policy_id=self.policy_id,
            expected_policy_version=self.expected_policy_version,
        )


class RuntimeActionResourceResponse(BaseModel):
    resource_type: str
    resource_reference: str


class RuntimeActionAuthorizationResponse(BaseModel):
    schema_version: str
    decision_id: str
    outcome: Literal["ALLOW", "DENY"]
    reason_code: str
    policy_id: str | None = None
    policy_version: str | None = None
    decision_at: datetime
    expires_at: datetime
    execution_id: str
    correlation_id: str | None = None
    action_id: str
    resource: RuntimeActionResourceResponse
    actor_id: str
    idempotency_key: str
    request_fingerprint: str
    delegation_id: str | None = None
    delegation_version: str | None = None
    delegation_digest: str | None = None
    tool_arguments_digest: str | None = None
    evaluated_policies: list[dict[str, str]] = Field(default_factory=list)
