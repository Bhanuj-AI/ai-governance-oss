from __future__ import annotations

import pytest

from ai_governance.settings_control.domain import (
    SettingContext,
    SettingEnvironmentOverride,
    SettingReadOnly,
    SettingScope,
    SettingSource,
    SettingValidationError,
    SettingVersionConflict,
)
from ai_governance.settings_control.repository import InMemorySettingsRepository
from ai_governance.settings_control.registry import SETTINGS_REGISTRY
from ai_governance.settings_control.service import ConfigurationService
from ai_governance.authorization.contracts import AuthorizationEnforcementDecision
from ai_governance.tenancy.domain import TenantContext
from ai_governance.tenancy.errors import AuthorizationDenied


def test_scoped_resolution_precedence_and_runtime_audit() -> None:
    repository = InMemorySettingsRepository()
    service = ConfigurationService(repository, {})
    context = SettingContext("org-1", "project-1")

    assert (
        service.resolve("mcp.dry_run_default", context).source is SettingSource.DEFAULT
    )
    system = service.update(
        "mcp.dry_run_default", True, "actor-1", "Safe system default", 0
    )
    assert system.source is SettingSource.RUNTIME_SYSTEM
    organization = service.update(
        "mcp.dry_run_default",
        False,
        "actor-1",
        "Organization automation",
        0,
        SettingScope.ORGANIZATION,
        context,
    )
    assert organization.source is SettingSource.RUNTIME_ORGANIZATION
    project = service.resolve("mcp.dry_run_default", context, SettingScope.PROJECT)
    assert project.effective_value is False
    assert project.inherited_from is SettingScope.ORGANIZATION
    assert project.version is None

    service.update(
        "mcp.dry_run_default",
        True,
        "actor-2",
        "Project safety",
        0,
        SettingScope.PROJECT,
        context,
    )
    resolved = service.resolve("mcp.dry_run_default", context, SettingScope.PROJECT)
    assert resolved.effective_value is True
    assert resolved.source is SettingSource.RUNTIME_PROJECT
    assert repository.list_audit()[0].scope is SettingScope.PROJECT


def test_environment_wins_and_blocks_runtime_updates() -> None:
    service = ConfigurationService(
        InMemorySettingsRepository(), {"AI_GOVERNANCE_MCP_DRY_RUN_DEFAULT": "true"}
    )
    assert service.get("mcp.dry_run_default") is True
    with pytest.raises(SettingEnvironmentOverride):
        service.update("mcp.dry_run_default", False, "actor", "Blocked", 0)


def test_validation_static_and_runtime_consumer_contract() -> None:
    service = ConfigurationService(InMemorySettingsRepository(), {})
    with pytest.raises(SettingValidationError):
        service.validate("jobs.worker_concurrency", 0)
    with pytest.raises(SettingValidationError):
        service.validate("jobs.retry_delay", "soon")
    with pytest.raises(SettingReadOnly):
        service.update("system.version", "2.0.0", "actor-1", "Invalid", 0)
    assert all(
        not definition.mutable or definition.runtime_applied
        for definition in SETTINGS_REGISTRY.values()
    )


def test_runtime_model_provider_allow_list_is_validated() -> None:
    service = ConfigurationService(InMemorySettingsRepository(), {})
    context = SettingContext("org-1", "project-1")

    assert service.validate(
        "model_registry.allowed_runtime_providers",
        ["openai", "aws_bedrock", "custom"],
    ) == ["openai", "aws_bedrock", "custom"]

    with pytest.raises(SettingValidationError):
        service.validate(
            "model_registry.allowed_runtime_providers",
            ["OpenAI"],
        )

    service.update(
        "model_registry.allowed_runtime_providers",
        ["aws_bedrock", "custom"],
        "actor-1",
        "Restrict managed registrations to approved runtimes",
        0,
        SettingScope.PROJECT,
        context,
    )
    assert service.get("model_registry.allowed_runtime_providers", context) == [
        "aws_bedrock",
        "custom",
    ]


def test_compare_and_set_rejects_stale_writer() -> None:
    service = ConfigurationService(InMemorySettingsRepository(), {})
    service.update("mcp.dry_run_default", True, "actor-1", "First", 0)
    with pytest.raises(SettingVersionConflict) as error:
        service.update("mcp.dry_run_default", False, "actor-2", "Stale", 0)
    assert error.value.current_version == 1


def test_plugin_authorization_can_deny_setting_update_before_persistence() -> None:
    repository = InMemorySettingsRepository()
    service = ConfigurationService(
        repository,
        {},
        authorization_enforcers=(_DenySettingUpdate(),),
    )
    context = TenantContext("org-1", "project-1", "actor-1", "request-1")

    with pytest.raises(AuthorizationDenied):
        service.update(
            "mcp.dry_run_default",
            True,
            "actor-1",
            "Test authorization enforcement",
            0,
            SettingScope.PROJECT,
            SettingContext("org-1", "project-1"),
            context,
        )

    assert repository.get(
        "mcp.dry_run_default", SettingScope.PROJECT, "project-1"
    ) is None


class _DenySettingUpdate:
    def authorize(self, request):
        assert request.action == "settings.update"
        assert request.resource.resource_type == "Setting"
        assert request.resource.attributes["sensitive"] is False
        return AuthorizationEnforcementDecision(False, "EXPLICIT_DENY_POLICY", "decision-1")


def test_replay_advisor_history_limit_is_live_and_project_scoped() -> None:
    service = ConfigurationService(InMemorySettingsRepository(), {})
    context = SettingContext("org-1", "project-1")

    assert service.get("intelligence.replay_history_limit", context) == 3
    resolved = service.update(
        "intelligence.replay_history_limit",
        8,
        "actor-1",
        "Need a wider replay trend window",
        0,
        SettingScope.PROJECT,
        context,
    )

    assert resolved.effective_value == 8
    assert resolved.definition.restart_required is False
    assert resolved.definition.runtime_applied is True


def test_enterprise_recommendation_priority_settings_are_live_and_validated() -> None:
    service = ConfigurationService(InMemorySettingsRepository(), {})
    context = SettingContext("org-1", "project-1")

    assert service.get("enterprise.recommendations.default_limit", context) == 20
    with pytest.raises(SettingValidationError):
        service.validate("enterprise.recommendations.governance_weight", 11)
    resolved = service.update(
        "enterprise.recommendations.governance_weight",
        1.5,
        "actor",
        "Prioritize governance",
        0,
        SettingScope.PROJECT,
        context,
    )
    assert resolved.effective_value == 1.5
    assert resolved.definition.runtime_applied is True


def test_intelligence_synthesizer_pricing_is_live_and_validated() -> None:
    service = ConfigurationService(InMemorySettingsRepository(), {})
    context = SettingContext("org-1", "project-1")

    assert (
        service.get("intelligence.synthesizer_pricing", context)["gpt-4.1-mini"][
            "input"
        ]
        == 0.40
    )
    with pytest.raises(SettingValidationError):
        service.validate(
            "intelligence.synthesizer_pricing", {"gpt-4.1-mini": {"input": 0.4}}
        )

    resolved = service.update(
        "intelligence.synthesizer_pricing",
        {"gpt-4.1-mini": {"input": 0.40, "cached_input": 0.10, "output": 1.60}},
        "actor-1",
        "Maintain the current provider price card",
        0,
        SettingScope.PROJECT,
        context,
    )

    assert resolved.definition.restart_required is False
    assert resolved.definition.runtime_applied is True
