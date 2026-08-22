from ai_governance.plugins import MiddlewareDefinition, PluginRegistry
from ai_governance.plugins.contracts import PermissionDefinition
from ai_governance.settings_control.domain import (
    SettingCategory,
    SettingDefinition,
    SettingValueType,
)


class FirstMiddleware:
    pass


class SecondMiddleware:
    pass


def test_contributions_are_deterministic_and_reject_duplicate_identities():
    registry = PluginRegistry()
    context = registry._context("example")
    context.contributions.middleware((MiddlewareDefinition(SecondMiddleware, 20), MiddlewareDefinition(FirstMiddleware, 10)))

    assert [item.middleware for item in sorted(registry.contributions.items("middleware"), key=lambda item: item.priority)] == [FirstMiddleware, SecondMiddleware]
    context.contributions.permissions((PermissionDefinition("sample.read"),))
    try:
        context.contributions.permissions((PermissionDefinition("sample.read"),))
    except RuntimeError as error:
        assert "Duplicate permissions" in str(error)
    else:
        raise AssertionError("duplicate permission contribution was accepted")


def test_extension_settings_are_available_to_existing_settings_registry():
    registry = PluginRegistry()
    context = registry._context("example")
    context.contributions.settings((SettingDefinition("plugin.example.enabled", SettingCategory.SYSTEM, "Enabled", "Example", SettingValueType.BOOLEAN, False, True),))
    registry.contributions.install(type("App", (), {"state": type("State", (), {"plugin_metrics": {}})(), "add_middleware": lambda *_: None})())

    from ai_governance.settings_control.registry import SETTINGS_REGISTRY
    assert SETTINGS_REGISTRY["plugin.example.enabled"].default_value is False
