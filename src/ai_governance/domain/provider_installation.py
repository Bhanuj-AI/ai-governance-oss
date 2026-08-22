"""Tenant-scoped configuration for one shipped evaluation-provider type."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ai_governance.providers.provider_descriptor import (
    normalize_provider_name,
    scrub_sensitive_metadata,
)

_SUPPORTED_SECRET_REFERENCE_SCHEMES = (
    "env://",
    "vault://",
    "aws-secretsmanager://",
    "keycloak://",
)


@dataclass(frozen=True)
class ProviderInstallation:
    """A durable, tenant-owned configuration of a shipped provider adapter.

    ``provider_type`` is resolved from the immutable runtime registry. ``settings``
    are non-sensitive adapter settings; credentials are represented only by
    ``secret_refs`` and are resolved by the runtime immediately before use.
    """

    installation_id: str
    provider_type: str
    adapter_version: str
    display_name: str
    settings: Mapping[str, Any]
    secret_refs: Mapping[str, str]
    enabled: bool
    organization_id: str
    project_id: str | None
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    version: int = 1

    def __post_init__(self) -> None:
        for field_name, value in (
            ("installation_id", self.installation_id),
            ("adapter_version", self.adapter_version),
            ("display_name", self.display_name),
            ("organization_id", self.organization_id),
            ("created_by", self.created_by),
            ("updated_by", self.updated_by),
        ):
            if not value.strip():
                raise ValueError(f"Provider installation {field_name} must not be empty.")
        if self.project_id is not None and not self.project_id.strip():
            raise ValueError("Provider installation project_id must not be blank.")

        if self.version < 1:
            raise ValueError("Provider installation version must be at least one.")
        if self.updated_at < self.created_at:
            raise ValueError("Provider installation updated_at must not precede created_at.")

        provider_type = normalize_provider_name(self.provider_type)
        if not provider_type:
            raise ValueError("Provider installation provider_type must not be empty.")
        object.__setattr__(self, "provider_type", provider_type)

        settings = dict(self.settings)
        if scrub_sensitive_metadata(settings) != settings:
            raise ValueError("Provider installation settings must not contain secrets; use secret_refs.")
        object.__setattr__(self, "settings", settings)

        refs = {str(key): str(value) for key, value in self.secret_refs.items()}
        for key, reference in refs.items():
            if not key.strip() or not reference.startswith(_SUPPORTED_SECRET_REFERENCE_SCHEMES):
                raise ValueError(
                    "Provider installation secret_refs must use env://, vault://, "
                    "aws-secretsmanager://, or keycloak:// references."
                )
        object.__setattr__(self, "secret_refs", refs)
