from __future__ import annotations

import asyncio
import os
import platform
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, cast

from ai_governance.authorization.contracts import (
    AuthorizationEnforcementRequest,
    AuthorizationEnforcer,
    AuthorizationResourceFacts,
)
from ai_governance.tenancy.domain import TenantContext
from ai_governance.tenancy.errors import AuthorizationDenied
from ai_governance.transactions import TransactionContext

from .domain import (
    ResolvedSetting,
    SettingContext,
    SettingEnvironmentOverride,
    SettingNotFound,
    SettingReadOnly,
    SettingScope,
    SettingScopeInvalid,
    SettingSource,
)
from .registry import SETTINGS_REGISTRY, parse_value
from .repository import SettingsRepository

if TYPE_CHECKING:
    from ai_governance.events import EventPublisher


class SettingsMetrics:
    def __init__(self) -> None:
        self.settings_updates_total = 0
        self.settings_validation_failures_total = 0
        self.settings_environment_overrides_total = 0

    def snapshot(self) -> dict[str, int]:
        return vars(self).copy()


METRICS = SettingsMetrics()


class ConfigurationService:
    def __init__(
        self,
        repository: SettingsRepository,
        environment: Mapping[str, str] | None = None,
        event_publisher: EventPublisher | None = None,
        authorization_enforcers: tuple[AuthorizationEnforcer, ...] = (),
    ) -> None:
        self.repository = repository
        self.environment = environment if environment is not None else os.environ
        self._event_publisher = event_publisher
        self._authorization_enforcers = authorization_enforcers

    def get(self, key: str, context: SettingContext | None = None) -> Any:
        return self.resolve(key, context=context).effective_value

    def resolve(
        self,
        key: str,
        context: SettingContext | None = None,
        edit_scope: SettingScope = SettingScope.SYSTEM,
    ) -> ResolvedSetting:
        definition = SETTINGS_REGISTRY.get(key)
        if not definition:
            raise SettingNotFound(key)
        context = context or SettingContext()
        edit_scope_id = self._scope_id(edit_scope, context)
        if edit_scope not in definition.allowed_scopes:
            edit_scope, edit_scope_id = SettingScope.SYSTEM, ""
        edited = self.repository.get(key, edit_scope, edit_scope_id)
        env_value = (
            self.environment.get(definition.environment_variable)
            if definition.environment_variable
            else None
        )
        inherited_from: SettingScope | None = None
        if env_value is not None:
            METRICS.settings_environment_overrides_total += 1
            effective = self._environment_value(key, env_value)
            source = SettingSource.ENVIRONMENT
        else:
            inherited = self._resolve_runtime(key, definition.allowed_scopes, context)
            if inherited:
                effective = inherited.value
                inherited_from = inherited.scope
                source = {
                    SettingScope.SYSTEM: SettingSource.RUNTIME_SYSTEM,
                    SettingScope.ORGANIZATION: SettingSource.RUNTIME_ORGANIZATION,
                    SettingScope.PROJECT: SettingSource.RUNTIME_PROJECT,
                }[inherited.scope]
            else:
                effective = self._computed_default(key, definition.default_value)
                source = SettingSource.DEFAULT
        if definition.sensitive and env_value is not None:
            effective = "connected"
        return ResolvedSetting(
            definition,
            edit_scope,
            edit_scope_id,
            edited.value if edited else None,
            effective,
            source,
            inherited_from,
            edited.version if edited else None,
            edited.updated_by if edited else None,
            edited.updated_at if edited else None,
        )

    def list(
        self,
        category: str | None = None,
        context: SettingContext | None = None,
        edit_scope: SettingScope = SettingScope.SYSTEM,
    ) -> list[ResolvedSetting]:
        values = [self.resolve(key, context, edit_scope) for key in SETTINGS_REGISTRY]
        return [
            item
            for item in values
            if not category
            or item.definition.category.value.lower() == category.lower()
        ]

    def categories(self) -> list[dict[str, Any]]:
        category_type = type(next(iter(SETTINGS_REGISTRY.values())).category)
        return [
            {
                "name": category.value,
                "key": category.name.lower(),
                "setting_count": sum(
                    1
                    for item in SETTINGS_REGISTRY.values()
                    if item.category is category
                ),
            }
            for category in category_type
        ]

    def validate(self, key: str, value: Any) -> Any:
        definition = SETTINGS_REGISTRY.get(key)
        if not definition:
            raise SettingNotFound(key)
        try:
            return parse_value(definition, value)
        except Exception:
            METRICS.settings_validation_failures_total += 1
            raise

    def update(
        self,
        key: str,
        value: Any,
        actor_id: str,
        reason: str,
        expected_version: int,
        scope: SettingScope = SettingScope.SYSTEM,
        context: SettingContext | None = None,
        tenant_context: TenantContext | None = None,
    ) -> ResolvedSetting:
        definition = SETTINGS_REGISTRY.get(key)
        if not definition:
            raise SettingNotFound(key)
        if not definition.mutable:
            raise SettingReadOnly(key)
        if not definition.runtime_applied:
            raise SettingReadOnly(f"{key} has no live runtime consumer")
        if scope not in definition.allowed_scopes:
            raise SettingScopeInvalid(f"{key} does not support {scope.value} scope")
        if (
            definition.environment_variable
            and definition.environment_variable in self.environment
        ):
            raise SettingEnvironmentOverride(key)
        context = context or SettingContext()
        scope_id = self._scope_id(scope, context)
        self._enforce_update(
            definition=definition,
            key=key,
            scope=scope,
            scope_id=scope_id,
            tenant_context=tenant_context,
        )
        parsed = self.validate(key, value)
        transaction_factory = getattr(self.repository, "transaction", None)
        if self._event_publisher is not None and callable(transaction_factory):
            transaction_context_factory = cast(
                Callable[[], AbstractContextManager[TransactionContext]],
                transaction_factory,
            )
            with transaction_context_factory() as transaction:
                saved = self.repository.save(
                    key,
                    scope,
                    scope_id,
                    parsed,
                    actor_id,
                    reason,
                    expected_version,
                    transaction=transaction,
                )
                asyncio.run(
                    self._event_publisher.publish_in_transaction(
                        self._setting_changed_event(
                            key, scope, scope_id, context, actor_id,
                            expected_version, saved.version, saved.updated_at,
                            definition.sensitive,
                        ),
                        transaction,
                    )
                )
        else:
            saved = self.repository.save(
                key, scope, scope_id, parsed, actor_id, reason, expected_version
            )
            if self._event_publisher is not None:
                asyncio.run(
                    self._event_publisher.publish(
                        self._setting_changed_event(
                            key, scope, scope_id, context, actor_id,
                            expected_version, saved.version, saved.updated_at,
                            definition.sensitive,
                        )
                    )
                )
        METRICS.settings_updates_total += 1
        return self.resolve(key, context, scope)

    def _enforce_update(
        self,
        *,
        definition,
        key: str,
        scope: SettingScope,
        scope_id: str,
        tenant_context: TenantContext | None,
    ) -> None:
        """Apply optional plugin constraints to an already RBAC-authorized update."""
        if not self._authorization_enforcers:
            return
        if tenant_context is None:
            raise AuthorizationDenied(_DeniedAuthorizationDecision("TENANT_CONTEXT_MISSING"))
        request = AuthorizationEnforcementRequest(
            context=tenant_context,
            action="settings.update",
            resource=AuthorizationResourceFacts(
                resource_type="Setting",
                resource_id=f"{scope.value}:{scope_id}:{key}",
                organization_id=tenant_context.organization_id,
                project_id=tenant_context.project_id,
                lifecycle_state=scope.value,
                attributes={
                    "category": definition.category.value,
                    "sensitive": definition.sensitive,
                },
            ),
        )
        for enforcer in self._authorization_enforcers:
            decision = enforcer.authorize(request)
            if not decision.allowed:
                raise AuthorizationDenied(decision)

    @staticmethod
    def _setting_changed_event(
        key: str,
        scope: SettingScope,
        scope_id: str,
        context: SettingContext,
        actor_id: str,
        previous_version: int,
        new_version: int,
        changed_at,
        sensitive: bool,
    ):
        """Build redacted generic metadata for a settings lifecycle mutation."""
        # Keep this import lazy: settings control participates in Core bootstrap
        # before some optional SPI providers complete their imports.
        from ai_governance.events import ResourceLifecycleEvent

        return ResourceLifecycleEvent(
            tenant={
                "tenant_id": context.organization_id or "system",
                "organization_id": context.organization_id or "",
                "project_id": context.project_id or "",
            },
            resource_kind="setting",
            resource_id=f"{scope.value}:{scope_id}:{key}",
            state="changed",
            payload={
                "key": key,
                "scope_type": scope.value,
                "scope_id": scope_id,
                "previous_effective_version": previous_version,
                "new_version": new_version,
                "changed_by": actor_id,
                "changed_at": changed_at.isoformat(),
                "sensitive": sensitive,
                "request_id": None,
            },
        )

    def _resolve_runtime(
        self,
        key: str,
        allowed_scopes: tuple[SettingScope, ...],
        context: SettingContext,
    ):
        candidates = (
            (SettingScope.PROJECT, context.project_id),
            (SettingScope.ORGANIZATION, context.organization_id),
            (SettingScope.SYSTEM, ""),
        )
        for scope, scope_id in candidates:
            if scope in allowed_scopes and scope_id is not None:
                item = self.repository.get(key, scope, scope_id)
                if item:
                    return item
        return None

    @staticmethod
    def _scope_id(scope: SettingScope, context: SettingContext) -> str:
        if scope is SettingScope.SYSTEM:
            return ""
        if scope is SettingScope.ORGANIZATION and context.organization_id:
            return context.organization_id
        if scope is SettingScope.PROJECT and context.project_id:
            return context.project_id
        raise SettingScopeInvalid(
            f"{scope.value} scope requires matching tenant context"
        )

    def _environment_value(self, key: str, value: str) -> Any:
        definition = SETTINGS_REGISTRY[key]
        if key.startswith("integrations."):
            return "connected" if value.strip() else "disconnected"
        return parse_value(definition, value)

    @staticmethod
    def _computed_default(key: str, default: Any) -> Any:
        return platform.python_version() if key == "system.python_version" else default


class _DeniedAuthorizationDecision:
    """Minimal generic denial shape used when request tenant context is absent."""

    allowed = False
    decision_id = None

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
