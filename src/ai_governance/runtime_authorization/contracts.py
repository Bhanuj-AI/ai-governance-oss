"""Durable, privacy-bounded contracts for one runtime tool operation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

RUNTIME_ACTION_AUTHORIZATION_SCHEMA_VERSION = "runtime-action-authorization/v1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CONTEXT_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_MAX_CONTEXT_FACTS = 32
_MAX_CONTEXT_STRING_LENGTH = 256
_MAX_RESOURCE_REFERENCE_LENGTH = 512
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


class RuntimeActionAuthorizationOutcome(str, Enum):
    """The only authoritative outcomes in the initial public contract."""

    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass(frozen=True)
class RuntimeActionResource:
    """A bounded reference to the resource an operation would affect."""

    resource_type: str
    resource_reference: str

    def __post_init__(self) -> None:
        _require_identifier("resource_type", self.resource_type)
        _require_non_blank("resource_reference", self.resource_reference)
        if len(self.resource_reference) > _MAX_RESOURCE_REFERENCE_LENGTH:
            raise ValueError(
                "resource_reference must not exceed "
                f"{_MAX_RESOURCE_REFERENCE_LENGTH} characters."
            )


@dataclass(frozen=True)
class RuntimeActionAuthorizationRequest:
    """One idempotent request to authorize one consequential operation.

    Tenant and actor are deliberately absent: they are always supplied by a
    validated :class:`TenantContext` at the service boundary.
    """

    execution_id: str
    action_id: str
    resource: RuntimeActionResource
    idempotency_key: str
    context: Mapping[str, str | int | float | bool] = field(default_factory=dict)
    correlation_id: str | None = None
    policy_id: str | None = None
    expected_policy_version: str | None = None
    schema_version: str = RUNTIME_ACTION_AUTHORIZATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_ACTION_AUTHORIZATION_SCHEMA_VERSION:
            raise ValueError("Unsupported runtime action authorization schema version.")
        _require_identifier("execution_id", self.execution_id)
        _require_identifier("action_id", self.action_id)
        _require_identifier("idempotency_key", self.idempotency_key)
        if not isinstance(self.resource, RuntimeActionResource):
            raise TypeError("resource must be a RuntimeActionResource.")
        if self.correlation_id is not None:
            _require_identifier("correlation_id", self.correlation_id)
        if self.policy_id is not None:
            _require_identifier("policy_id", self.policy_id)
        if self.expected_policy_version is not None:
            _require_identifier("expected_policy_version", self.expected_policy_version)
        if self.expected_policy_version is not None and self.policy_id is None:
            raise ValueError("expected_policy_version requires policy_id.")
        object.__setattr__(self, "context", _validated_context(self.context))

    def fingerprint(self) -> str:
        """Return a stable digest without retaining contextual fact values."""

        payload = {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "action_id": self.action_id,
            "resource_type": self.resource.resource_type,
            "resource_reference": self.resource.resource_reference,
            "context": dict(self.context),
            "correlation_id": self.correlation_id,
            "policy_id": self.policy_id,
            "expected_policy_version": self.expected_policy_version,
        }
        return _stable_digest(payload)

    def context_digest(self) -> str:
        return _stable_digest(dict(self.context))


@dataclass(frozen=True)
class RuntimeActionAuthorizationDecision:
    """Persisted decision bound to one operation, actor, and resource."""

    decision_id: str
    outcome: RuntimeActionAuthorizationOutcome | str
    reason_code: str
    execution_id: str
    correlation_id: str | None
    action_id: str
    resource: RuntimeActionResource
    actor_id: str
    idempotency_key: str
    request_fingerprint: str
    decided_at: datetime
    expires_at: datetime
    policy_id: str | None = None
    policy_version: str | None = None
    schema_version: str = RUNTIME_ACTION_AUTHORIZATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_ACTION_AUTHORIZATION_SCHEMA_VERSION:
            raise ValueError("Unsupported runtime action authorization schema version.")
        for name, value in (
            ("decision_id", self.decision_id),
            ("reason_code", self.reason_code),
            ("execution_id", self.execution_id),
            ("action_id", self.action_id),
            ("actor_id", self.actor_id),
            ("idempotency_key", self.idempotency_key),
            ("request_fingerprint", self.request_fingerprint),
        ):
            _require_identifier(name, value)
        if self.correlation_id is not None:
            _require_identifier("correlation_id", self.correlation_id)
        if self.policy_id is not None:
            _require_identifier("policy_id", self.policy_id)
        if self.policy_version is not None:
            _require_identifier("policy_version", self.policy_version)
        if not isinstance(self.resource, RuntimeActionResource):
            raise TypeError("resource must be a RuntimeActionResource.")
        if self.decided_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("decision timestamps must be timezone-aware.")
        if self.expires_at <= self.decided_at:
            raise ValueError("expires_at must be later than decided_at.")
        object.__setattr__(
            self,
            "outcome",
            RuntimeActionAuthorizationOutcome(self.outcome),
        )

    def is_valid_for(
        self,
        request: RuntimeActionAuthorizationRequest,
        *,
        actor_id: str,
        now: datetime,
    ) -> bool:
        """Verify a returned ALLOW before a runtime invokes its tool.

        This deliberately does not make a decision reusable for another
        operation: every bound field must match and an expired decision is
        invalid even if it was an ALLOW.
        """

        return (
            self.outcome is RuntimeActionAuthorizationOutcome.ALLOW
            and self.expires_at > now
            and self.matches_request(request, actor_id=actor_id)
        )

    def matches_request(
        self,
        request: RuntimeActionAuthorizationRequest,
        *,
        actor_id: str,
    ) -> bool:
        """Match immutable decision bindings without treating a DENY as valid."""

        return (
            self.execution_id == request.execution_id
            and self.action_id == request.action_id
            and self.resource == request.resource
            and self.actor_id == actor_id
            and self.idempotency_key == request.idempotency_key
            and self.request_fingerprint == request.fingerprint()
        )


def _validated_context(
    values: Mapping[str, str | int | float | bool],
) -> Mapping[str, str | int | float | bool]:
    if not isinstance(values, Mapping):
        raise TypeError("context must be a mapping of scalar facts.")
    if len(values) > _MAX_CONTEXT_FACTS:
        raise ValueError(
            f"context must not contain more than {_MAX_CONTEXT_FACTS} facts."
        )
    copied: dict[str, str | int | float | bool] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not _CONTEXT_KEY.fullmatch(key):
            raise ValueError(
                "context fact keys must be bounded alphanumeric identifiers."
            )
        normalized = key.lower().replace("-", "_").replace(" ", "_")
        if normalized in _SENSITIVE_CONTEXT_KEYS:
            raise ValueError(
                "context must not contain prompts, credentials, or reasoning."
            )
        if isinstance(value, str):
            if not value.strip() or len(value) > _MAX_CONTEXT_STRING_LENGTH:
                raise ValueError(
                    "context string facts must be non-blank and no longer than "
                    f"{_MAX_CONTEXT_STRING_LENGTH} characters."
                )
            copied[key] = value
        elif isinstance(value, (bool, int, float)):
            copied[key] = value
        else:
            raise TypeError(
                "context facts must be scalar strings, numbers, or booleans."
            )
    return MappingProxyType(copied)


def _require_identifier(name: str, value: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(
            f"{name} must be a bounded identifier containing only letters, "
            "numbers, '.', '_', ':', or '-'."
        )


def _require_non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank.")


def _stable_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
