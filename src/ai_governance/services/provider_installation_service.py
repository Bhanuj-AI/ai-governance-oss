"""Application service for tenant-managed evaluation provider installations."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from ai_governance.domain.provider_installation import ProviderInstallation
from ai_governance.providers.errors import ProviderNotFoundError
from ai_governance.providers.provider_registry import EvaluationProviderRegistry
from ai_governance.repositories.provider_installation_repository import ProviderInstallationRepository
from ai_governance.tenancy.domain import TenantContext


class ProviderInstallationNotFoundError(Exception):
    pass


class ProviderInstallationDisabledError(Exception):
    pass


class ProviderInstallationTypeUnavailableError(Exception):
    pass


class SecretReferenceResolver(Protocol):
    def resolve(self, reference: str) -> str: ...


class EnvironmentSecretReferenceResolver:
    """Resolve local ``env://NAME`` references without persisting secret values."""

    def resolve(self, reference: str) -> str:
        if not reference.startswith("env://"):
            raise ValueError(
                f"Secret reference '{reference}' is unavailable in this runtime."
            )
        name = reference.removeprefix("env://").strip()
        value = os.getenv(name)
        if not name or value is None or not value.strip():
            raise ValueError(f"Secret reference '{reference}' could not be resolved.")
        return value


class ProviderInstallationService:
    """Manage installations while leaving runtime provider types immutable."""

    def __init__(
        self,
        repository: ProviderInstallationRepository,
        provider_registry: EvaluationProviderRegistry,
        secret_resolver: SecretReferenceResolver | None = None,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._provider_registry = provider_registry
        self._secret_resolver = secret_resolver or EnvironmentSecretReferenceResolver()
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))

    def list(self, context: TenantContext) -> list[ProviderInstallation]:
        return [
            self._hydrate_legacy_adapter_version(item)
            for item in self._repository.list_for_scope(
                context.organization_id, context.project_id
            )
        ]

    def get(self, installation_id: str, context: TenantContext) -> ProviderInstallation:
        item = self._repository.find_by_id(
            installation_id, context.organization_id, context.project_id
        )
        if item is None:
            raise ProviderInstallationNotFoundError(
                f"Provider installation '{installation_id}' was not found."
            )
        return self._hydrate_legacy_adapter_version(item)

    def create(
        self,
        *,
        provider_type: str,
        display_name: str,
        settings: Mapping[str, Any],
        secret_refs: Mapping[str, str],
        enabled: bool,
        project_id: str | None = None,
        context: TenantContext,
    ) -> ProviderInstallation:
        provider = self._require_provider_type(provider_type)
        if enabled:
            self.validate_configuration(
                provider_type=provider_type,
                settings=settings,
                secret_refs=secret_refs,
                context=context,
            )
        now = self._clock()
        return self._repository.save(
            ProviderInstallation(
                installation_id=self._id_generator(),
                provider_type=provider_type,
                adapter_version=provider.descriptor.adapter_version,
                display_name=display_name,
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
        installation_id: str,
        *,
        display_name: str | None,
        settings: Mapping[str, Any] | None,
        secret_refs: Mapping[str, str] | None,
        enabled: bool | None,
        context: TenantContext,
    ) -> ProviderInstallation:
        existing = self.get(installation_id, context)
        updated = replace(
            existing,
            display_name=display_name if display_name is not None else existing.display_name,
            settings=dict(settings) if settings is not None else existing.settings,
            secret_refs=dict(secret_refs) if secret_refs is not None else existing.secret_refs,
            enabled=enabled if enabled is not None else existing.enabled,
            updated_by=context.actor_id,
            updated_at=self._clock(),
        )
        if updated.enabled:
            self.validate_configuration(
                provider_type=updated.provider_type,
                settings=updated.settings,
                secret_refs=updated.secret_refs,
                context=context,
            )
        return self._repository.save(updated)

    def validate_configuration(
        self,
        *,
        provider_type: str,
        settings: Mapping[str, Any],
        secret_refs: Mapping[str, str],
        context: TenantContext,
    ) -> None:
        """Resolve references and initialize an adapter without persisting a run."""
        provider = self._require_provider_type(provider_type)
        self._validate_schema(provider.descriptor.configuration_schema, settings, secret_refs)
        resolved_config = dict(settings)
        for key, reference in secret_refs.items():
            resolved_config[key] = self._secret_resolver.resolve(reference)
        validate = getattr(provider, "validate_configuration", None)
        if callable(validate):
            validate(resolved_config)

    def resolve_runtime_config(
        self, installation_id: str, context: TenantContext
    ) -> tuple[ProviderInstallation, dict[str, Any]]:
        """Resolve one enabled installation immediately before adapter invocation."""
        installation = self.get(installation_id, context)
        if not installation.enabled:
            raise ProviderInstallationDisabledError(
                f"Provider installation '{installation.display_name}' is disabled."
            )
        self._require_provider_type(installation.provider_type)
        config = dict(installation.settings)
        for key, reference in installation.secret_refs.items():
            config[key] = self._secret_resolver.resolve(reference)
        return installation, config

    def resolve_provider_type(
        self, installation_id: str, context: TenantContext
    ) -> ProviderInstallation:
        """Resolve an enabled installation without dereferencing credentials."""
        installation = self.get(installation_id, context)
        if not installation.enabled:
            raise ProviderInstallationDisabledError(
                f"Provider installation '{installation.display_name}' is disabled."
            )
        self._require_provider_type(installation.provider_type)
        return installation

    def _require_provider_type(self, provider_type: str):
        try:
            return self._provider_registry.get(provider_type)
        except ProviderNotFoundError as exc:
            raise ProviderInstallationTypeUnavailableError(
                f"Provider type '{provider_type}' is not available in this deployment."
            ) from exc

    def _hydrate_legacy_adapter_version(
        self, installation: ProviderInstallation
    ) -> ProviderInstallation:
        """Show a useful version for records created before version capture existed.

        The old record cannot reveal its historical target version. We therefore
        project the currently shipped adapter version without writing an
        artificial operator update/audit record. The next real update persists it.
        """
        if installation.adapter_version != "unknown":
            return installation
        try:
            provider = self._provider_registry.get(installation.provider_type)
        except ProviderNotFoundError:
            return installation
        return replace(
            installation,
            adapter_version=provider.descriptor.adapter_version,
        )

    @staticmethod
    def _validate_schema(
        schema: Mapping[str, Any],
        settings: Mapping[str, Any],
        secret_refs: Mapping[str, str],
    ) -> None:
        for label, values in (("settings", settings), ("secret_refs", secret_refs)):
            section = schema.get(label, {})
            required = section.get("required", []) if isinstance(section, Mapping) else []
            missing = [key for key in required if not str(values.get(key, "")).strip()]
            if missing:
                raise ValueError(
                    f"Provider configuration requires {label}: {', '.join(missing)}."
                )
