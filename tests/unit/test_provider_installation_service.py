from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.providers import EvaluationProviderRegistry, MockEvaluationProvider
from ai_governance.repositories.settings_provider_installation_repository import (
    SettingsProviderInstallationRepository,
)
from ai_governance.services.provider_installation_service import (
    ProviderInstallationNotFoundError,
    ProviderInstallationService,
)
from ai_governance.settings_control.domain import SettingScope
from ai_governance.settings_control.repository import InMemorySettingsRepository
from ai_governance.tenancy.domain import TenantContext


def _context(org: str = "org-a", project: str = "project-a") -> TenantContext:
    return TenantContext(org, project, "platform-admin", "request-1")


def _service(environment: dict[str, str] | None = None) -> ProviderInstallationService:
    registry = EvaluationProviderRegistry()
    registry.register(MockEvaluationProvider())
    service = ProviderInstallationService(
        SettingsProviderInstallationRepository(InMemorySettingsRepository()),
        registry,
        id_generator=lambda: "installation-1",
        clock=lambda: datetime(2026, 8, 6, tzinfo=UTC),
    )
    return service


def test_installation_is_tenant_scoped_and_persists_secret_references_only() -> None:
    service = _service()
    created = service.create(
        provider_type="Mock",
        display_name="Mock Production",
        settings={"mode": "deterministic"},
        secret_refs={"api_key": "env://MOCK_API_KEY"},
        enabled=False,
        context=_context(),
    )

    assert created.provider_type == "mock"
    assert created.secret_refs == {"api_key": "env://MOCK_API_KEY"}
    assert service.list(_context()) == [created]
    assert service.list(_context("org-a", "project-b")) == [created]
    with pytest.raises(ProviderInstallationNotFoundError):
        service.get(created.installation_id, _context("org-b", "project-b"))


def test_installation_rejects_secret_values_in_settings() -> None:
    service = _service()

    with pytest.raises(ValueError, match="must not contain secrets"):
        service.create(
            provider_type="mock",
            display_name="Unsafe",
            settings={"api_key": "not-a-reference"},
            secret_refs={},
            enabled=True,
            context=_context(),
        )


def test_legacy_installation_projects_the_current_adapter_version() -> None:
    settings = InMemorySettingsRepository()
    settings.save(
        key="provider_installation.legacy-trulens",
        scope=SettingScope.ORGANIZATION,
        scope_id="org-a",
        value={
            "installation_id": "legacy-trulens",
            "provider_type": "mock",
            "display_name": "Legacy Mock",
            "settings": {},
            "secret_refs": {},
            "enabled": True,
            "organization_id": "org-a",
            "project_id": None,
            "created_by": "platform-admin",
            "updated_by": "platform-admin",
            "created_at": "2026-08-06T00:00:00+00:00",
            "updated_at": "2026-08-06T00:00:00+00:00",
        },
        actor_id="platform-admin",
        reason="legacy fixture",
        expected_version=0,
    )
    registry = EvaluationProviderRegistry()
    registry.register(MockEvaluationProvider())
    service = ProviderInstallationService(
        SettingsProviderInstallationRepository(settings), registry
    )

    assert service.list(_context())[0].adapter_version == "1.0.0"
