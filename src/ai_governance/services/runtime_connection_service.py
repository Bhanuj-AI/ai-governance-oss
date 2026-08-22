"""Application service for tenant-owned model runtime connections."""

from __future__ import annotations

import os
from collections.abc import Callable, Collection, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from ai_governance.domain.models import runtime_model_provider_key
from ai_governance.domain.runtime_connection import (
    RuntimeConnection,
    RuntimeConnectionTestStatus,
)
from ai_governance.repositories.runtime_connection_repository import (
    RuntimeConnectionRepository,
)
from ai_governance.tenancy.domain import TenantContext


class RuntimeConnectionNotFoundError(Exception):
    """Raised when a tenant-scoped runtime connection cannot be found."""


class RuntimeConnectionDisabledError(Exception):
    """Raised when an invocation attempts to use a disabled connection."""


class RuntimeConnectionProviderUnavailableError(Exception):
    """Raised when a provider has no OSS runtime connection adapter."""


class RuntimeConnectionProviderNotAllowedError(Exception):
    """Raised when tenant provider policy disallows a runtime connection."""


class RuntimeConnectionProviderMismatchError(Exception):
    """Raised when a connection cannot invoke the registered model provider."""


class SecretReferenceResolver(Protocol):
    def resolve(self, reference: str) -> str: ...


class EnvironmentSecretReferenceResolver:
    """Resolve local ``env://NAME`` references without persisting key values."""

    def resolve(self, reference: str) -> str:
        if not reference.startswith("env://"):
            raise ValueError("The configured secret reference is unavailable in this runtime.")
        name = reference.removeprefix("env://").strip()
        value = os.getenv(name)
        if not name or value is None or not value.strip():
            raise ValueError("The configured secret reference could not be resolved.")
        return value


_RUNTIME_CONNECTION_SCHEMAS = {
    "openai": {
        "settings": frozenset({"base_url", "organization"}),
        "required_secret_refs": frozenset({"api_key"}),
    },
    "anthropic": {
        "settings": frozenset({"base_url"}),
        "required_secret_refs": frozenset({"api_key"}),
    },
    "custom": {
        "settings": frozenset({"base_url", "organization"}),
        "required_secret_refs": frozenset(),
    },
}


class RuntimeConnectionService:
    """Manage runtime connection identity, scope, and secret-reference policy.

    The OSS service validates OpenAI, Anthropic, and OpenAI-compatible custom
    connection configuration. Provider invocation stays in a future runtime
    adapter; resolved values are never persisted or returned by this service.
    """

    def __init__(
        self,
        repository: RuntimeConnectionRepository,
        secret_resolver: SecretReferenceResolver | None = None,
        allowed_runtime_providers: Callable[[TenantContext], Collection[str]] | None = None,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._secret_resolver = secret_resolver or EnvironmentSecretReferenceResolver()
        self._allowed_runtime_providers = allowed_runtime_providers
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))

    def list(self, context: TenantContext) -> list[RuntimeConnection]:
        return self._repository.list_for_scope(context.organization_id, context.project_id)

    def get(self, runtime_connection_id: str, context: TenantContext) -> RuntimeConnection:
        connection = self._repository.find_by_id(
            runtime_connection_id, context.organization_id, context.project_id
        )
        if connection is None:
            raise RuntimeConnectionNotFoundError(
                f"Runtime connection '{runtime_connection_id}' was not found."
            )
        return connection

    def create(
        self,
        *,
        display_name: str,
        provider: str,
        settings: Mapping[str, Any],
        secret_refs: Mapping[str, str],
        enabled: bool,
        project_id: str | None,
        context: TenantContext,
    ) -> RuntimeConnection:
        self._validate_configuration(
            provider, settings, secret_refs, context, resolve_secret_references=enabled
        )
        now = self._clock()
        return self._repository.save(
            RuntimeConnection(
                runtime_connection_id=self._id_generator(),
                display_name=display_name,
                provider=provider,
                settings=dict(settings),
                secret_refs=dict(secret_refs),
                enabled=enabled,
                organization_id=context.organization_id,
                project_id=project_id,
                created_by=context.actor_id,
                updated_by=context.actor_id,
                created_at=now,
                updated_at=now,
            )
        )

    def update(
        self,
        runtime_connection_id: str,
        *,
        display_name: str | None,
        settings: Mapping[str, Any] | None,
        secret_refs: Mapping[str, str] | None,
        enabled: bool | None,
        context: TenantContext,
    ) -> RuntimeConnection:
        existing = self.get(runtime_connection_id, context)
        updated = replace(
            existing,
            display_name=display_name if display_name is not None else existing.display_name,
            settings=dict(settings) if settings is not None else existing.settings,
            secret_refs=dict(secret_refs) if secret_refs is not None else existing.secret_refs,
            enabled=enabled if enabled is not None else existing.enabled,
            updated_by=context.actor_id,
            updated_at=self._clock(),
        )
        self._validate_configuration(
            updated.provider,
            updated.settings,
            updated.secret_refs,
            context,
            resolve_secret_references=updated.enabled,
        )
        return self._repository.save(updated)

    def test(self, runtime_connection_id: str, context: TenantContext) -> RuntimeConnection:
        """Record whether non-secret configuration and secret refs can be resolved.

        This deliberately performs no remote HTTP request. The initial OSS
        adapter validates local configuration only, avoiding an opaque network
        side effect during a settings operation. Invocation adapters own a
        provider-specific live request when they are introduced.
        """

        connection = self.get(runtime_connection_id, context)
        now = self._clock()
        try:
            self._validate_configuration(
                connection.provider,
                connection.settings,
                connection.secret_refs,
                context,
                resolve_secret_references=True,
            )
        except (RuntimeConnectionProviderUnavailableError, RuntimeConnectionProviderNotAllowedError, ValueError):
            return self._repository.save(
                replace(
                    connection,
                    last_tested_at=now,
                    last_test_status=RuntimeConnectionTestStatus.FAILED,
                    last_test_message="Configuration or secret-reference validation failed.",
                    updated_by=context.actor_id,
                    updated_at=now,
                )
            )
        return self._repository.save(
            replace(
                connection,
                last_tested_at=now,
                last_test_status=RuntimeConnectionTestStatus.SUCCEEDED,
                last_test_message="Configuration and secret references resolved successfully.",
                updated_by=context.actor_id,
                updated_at=now,
            )
        )

    def validate_configuration(
        self,
        *,
        provider: str,
        settings: Mapping[str, Any],
        secret_refs: Mapping[str, str],
        context: TenantContext,
    ) -> None:
        """Validate an unsaved connection without retaining any credential value."""

        self._validate_configuration(
            provider,
            settings,
            secret_refs,
            context,
            resolve_secret_references=True,
        )

    def resolve_runtime_config(
        self,
        runtime_connection_id: str,
        model_provider: str,
        context: TenantContext,
    ) -> tuple[RuntimeConnection, dict[str, Any]]:
        """Resolve one enabled connection for a compatible model invocation."""

        connection = self.get(runtime_connection_id, context)
        if not connection.enabled:
            raise RuntimeConnectionDisabledError(
                f"Runtime connection '{connection.display_name}' is disabled."
            )
        expected_provider = runtime_model_provider_key(model_provider)
        if expected_provider != connection.provider:
            raise RuntimeConnectionProviderMismatchError(
                "Runtime connection provider does not match the registered model provider."
            )
        self._validate_configuration(
            connection.provider,
            connection.settings,
            connection.secret_refs,
            context,
            resolve_secret_references=True,
        )
        resolved = dict(connection.settings)
        for key, reference in connection.secret_refs.items():
            resolved[key] = self._secret_resolver.resolve(reference)
        return connection, resolved

    def validate_model_compatibility(
        self,
        runtime_connection_id: str,
        model_provider: str,
        context: TenantContext,
    ) -> RuntimeConnection:
        """Verify that an enabled connection can serve a registered model.

        Candidate registration calls this without resolving a secret.  Secret
        resolution remains an execution-time concern so a candidate never
        captures credential material.
        """

        connection = self.get(runtime_connection_id, context)
        if not connection.enabled:
            raise RuntimeConnectionDisabledError(
                f"Runtime connection '{connection.display_name}' is disabled."
            )
        expected_provider = runtime_model_provider_key(model_provider)
        if expected_provider != connection.provider:
            raise RuntimeConnectionProviderMismatchError(
                "Runtime connection provider does not match the registered model provider."
            )
        return connection

    @staticmethod
    def supported_provider_keys() -> tuple[str, ...]:
        return tuple(_RUNTIME_CONNECTION_SCHEMAS)

    def allowed_provider_keys(self, context: TenantContext) -> tuple[str, ...]:
        supported = self.supported_provider_keys()
        if self._allowed_runtime_providers is None:
            return supported
        allowed = {
            key
            for value in self._allowed_runtime_providers(context)
            if (key := runtime_model_provider_key(value)) is not None
        }
        return tuple(provider for provider in supported if provider in allowed)

    def _validate_configuration(
        self,
        provider: str,
        settings: Mapping[str, Any],
        secret_refs: Mapping[str, str],
        context: TenantContext,
        resolve_secret_references: bool,
    ) -> None:
        provider_key = runtime_model_provider_key(provider)
        if provider_key not in _RUNTIME_CONNECTION_SCHEMAS:
            raise RuntimeConnectionProviderUnavailableError(
                f"Runtime provider '{provider}' is not available in OSS runtime connections."
            )
        if provider_key not in self.allowed_provider_keys(context):
            raise RuntimeConnectionProviderNotAllowedError(
                f"Runtime provider '{provider_key}' is not allowed in this tenant scope."
            )
        schema = _RUNTIME_CONNECTION_SCHEMAS[provider_key]
        unknown = set(settings) - schema["settings"]
        if unknown:
            raise ValueError(
                "Runtime connection settings contain unsupported fields: "
                + ", ".join(sorted(unknown))
                + "."
            )
        missing = schema["required_secret_refs"] - set(secret_refs)
        if missing:
            raise ValueError(
                "Runtime connection requires secret references: "
                + ", ".join(sorted(missing))
                + "."
            )
        if provider_key == "custom" and not str(settings.get("base_url", "")).strip():
            raise ValueError("Custom runtime connections require a base_url setting.")
        base_url = settings.get("base_url")
        if base_url is not None:
            parsed = urlparse(str(base_url))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Runtime connection base_url must be an absolute HTTP(S) URL.")
        if resolve_secret_references:
            for reference in secret_refs.values():
                self._secret_resolver.resolve(str(reference))
