"""Tenant-owned credentials and configuration for model-runtime invocation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from ai_governance.domain.models import runtime_model_provider_key

_SUPPORTED_SECRET_REFERENCE_SCHEMES = (
    "env://",
    "vault://",
    "aws-secretsmanager://",
    "keycloak://",
)
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
)


class RuntimeConnectionTestStatus(str, Enum):
    """Recorded result of the latest non-secret configuration test."""

    NOT_TESTED = "NOT_TESTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RuntimeConnection:
    """A separately versioned tenant resource used to invoke a model runtime.

    A connection is deliberately not part of a model version: credentials and
    endpoints rotate independently from the governed model definition. Only
    secret references are durable; their resolved values are held in memory by
    an invocation adapter for the duration of one request.
    """

    runtime_connection_id: str
    display_name: str
    provider: str
    settings: Mapping[str, Any]
    secret_refs: Mapping[str, str]
    enabled: bool
    organization_id: str
    project_id: str | None
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    last_tested_at: datetime | None = None
    last_test_status: RuntimeConnectionTestStatus = RuntimeConnectionTestStatus.NOT_TESTED
    last_test_message: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        for field_name, value in (
            ("runtime_connection_id", self.runtime_connection_id),
            ("display_name", self.display_name),
            ("organization_id", self.organization_id),
            ("created_by", self.created_by),
            ("updated_by", self.updated_by),
        ):
            if not value.strip():
                raise ValueError(f"Runtime connection {field_name} must not be empty.")
        if self.project_id is not None and not self.project_id.strip():
            raise ValueError("Runtime connection project_id must not be blank.")
        if self.version < 1:
            raise ValueError("Runtime connection version must be at least one.")
        if self.updated_at < self.created_at:
            raise ValueError("Runtime connection updated_at must not precede created_at.")
        if self.last_tested_at is not None and self.last_tested_at < self.created_at:
            raise ValueError("Runtime connection last_tested_at must not precede created_at.")

        provider = runtime_model_provider_key(self.provider)
        if provider is None:
            raise ValueError("Runtime connection provider must be a known runtime provider.")
        object.__setattr__(self, "provider", provider)

        settings = dict(self.settings)
        if _contains_sensitive_key(settings):
            raise ValueError("Runtime connection settings must not contain secrets; use secret_refs.")
        object.__setattr__(self, "settings", settings)

        refs = {str(key): str(value) for key, value in self.secret_refs.items()}
        for key, reference in refs.items():
            if not key.strip() or not reference.startswith(_SUPPORTED_SECRET_REFERENCE_SCHEMES):
                raise ValueError(
                    "Runtime connection secret_refs must use env://, vault://, "
                    "aws-secretsmanager://, or keycloak:// references."
                )
        object.__setattr__(self, "secret_refs", refs)

        if self.last_test_message is not None and len(self.last_test_message) > 500:
            raise ValueError("Runtime connection last_test_message must be at most 500 characters.")


def _contains_sensitive_key(values: Mapping[str, Any]) -> bool:
    for key, value in values.items():
        normalized = str(key).lower().replace("-", "_")
        if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
            return True
        if isinstance(value, Mapping) and _contains_sensitive_key(value):
            return True
    return False
