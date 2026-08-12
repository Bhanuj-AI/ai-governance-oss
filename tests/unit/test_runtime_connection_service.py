from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.repositories.settings_runtime_connection_repository import (
    SettingsRuntimeConnectionRepository,
)
from ai_governance.services.runtime_connection_service import (
    RuntimeConnectionDisabledError,
    RuntimeConnectionProviderMismatchError,
    RuntimeConnectionService,
)
from ai_governance.settings_control.repository import InMemorySettingsRepository
from ai_governance.tenancy.domain import TenantContext


class _SecretResolver:
    def resolve(self, reference: str) -> str:
        if reference == "env://AVAILABLE":
            return "resolved-secret"
        raise ValueError("unavailable")


def _context(org: str = "org-a", project: str = "project-a") -> TenantContext:
    return TenantContext(org, project, "governance-admin", "request-1")


def _service() -> RuntimeConnectionService:
    return RuntimeConnectionService(
        SettingsRuntimeConnectionRepository(InMemorySettingsRepository()),
        secret_resolver=_SecretResolver(),
        allowed_runtime_providers=lambda _: ("openai", "anthropic", "custom"),
        id_generator=lambda: "connection-1",
        clock=lambda: datetime(2026, 8, 11, tzinfo=UTC),
    )


def test_runtime_connection_is_scoped_and_persists_only_secret_references() -> None:
    service = _service()
    created = service.create(
        display_name="OpenAI Development",
        provider="openai",
        settings={"organization": "org_demo"},
        secret_refs={"api_key": "env://AVAILABLE"},
        enabled=True,
        project_id=None,
        context=_context(),
    )

    assert created.provider == "openai"
    assert created.secret_refs == {"api_key": "env://AVAILABLE"}
    assert "resolved-secret" not in str(created)
    assert service.list(_context()) == [created]
    assert service.list(_context("org-b", "project-b")) == []


def test_runtime_connection_tests_and_resolves_only_for_matching_model_provider() -> None:
    service = _service()
    created = service.create(
        display_name="OpenAI Development",
        provider="openai",
        settings={"base_url": "https://api.openai.com/v1"},
        secret_refs={"api_key": "env://AVAILABLE"},
        enabled=True,
        project_id="project-a",
        context=_context(),
    )

    tested = service.test(created.runtime_connection_id, _context())
    compatible = service.validate_model_compatibility(
        created.runtime_connection_id, "openai", _context()
    )
    connection, config = service.resolve_runtime_config(
        created.runtime_connection_id, "openai", _context()
    )

    assert tested.last_test_status.value == "SUCCEEDED"
    assert compatible.runtime_connection_id == created.runtime_connection_id
    assert connection == tested
    assert config["api_key"] == "resolved-secret"
    with pytest.raises(RuntimeConnectionProviderMismatchError):
        service.resolve_runtime_config(created.runtime_connection_id, "anthropic", _context())


def test_runtime_connection_records_failed_test_and_can_be_disabled_without_resolving_secret() -> None:
    service = _service()
    created = service.create(
        display_name="Offline OpenAI",
        provider="openai",
        settings={},
        secret_refs={"api_key": "env://UNAVAILABLE"},
        enabled=False,
        project_id="project-a",
        context=_context(),
    )

    tested = service.test(created.runtime_connection_id, _context())

    assert tested.last_test_status.value == "FAILED"
    with pytest.raises(RuntimeConnectionDisabledError):
        service.resolve_runtime_config(created.runtime_connection_id, "openai", _context())


def test_custom_runtime_connection_requires_an_endpoint() -> None:
    service = _service()

    with pytest.raises(ValueError, match="require a base_url"):
        service.create(
            display_name="Gateway",
            provider="custom",
            settings={},
            secret_refs={},
            enabled=False,
            project_id="project-a",
            context=_context(),
        )
