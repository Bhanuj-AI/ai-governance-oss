"""Coverage for plugin lifecycle bootstrap outside the API server."""

from __future__ import annotations

import pytest

from ai_governance.plugins import (
    ExtensionError,
    PluginMetadata,
    ReplayExecutionAdapterContribution,
    create_plugin_registry,
)


class _LifecyclePlugin:
    """Record generic lifecycle calls made by a standalone host."""

    metadata = PluginMetadata(
        name="worker-plugin",
        version="1.0.0",
        required_ai_governance_version=">=0",
    )

    def __init__(self) -> None:
        self.calls: list[str] = []

    def validate(self, context) -> None:
        self.calls.append("validate")

    def register(self, context) -> None:
        self.calls.append("register")

    def start(self, context) -> None:
        self.calls.append("start")

    def stop(self, context) -> None:
        self.calls.append("stop")


def test_plugin_registry_bootstrap_has_a_complete_lifecycle(monkeypatch) -> None:
    """Standalone hosts discover/register/start/stop through one helper."""
    plugin = _LifecyclePlugin()
    groups: list[str] = []

    class _EntryPoints:
        def select(self, *, group: str):
            groups.append(group)
            return ()

    monkeypatch.setattr(
        "ai_governance.plugins.registry.entry_points", lambda: _EntryPoints()
    )
    registry = create_plugin_registry(plugins=(plugin,))
    registry.start()
    registry.stop()

    assert plugin.calls == ["validate", "register", "start", "stop"]
    assert groups == [
        "bhanuj.governance.plugins",
        "ai_governance.plugins",
    ]


class _ReplayAdapter:
    name = "external-runtime/v1"


class _ReplayAdapterPlugin:
    metadata = PluginMetadata(
        name="external-runtime-plugin",
        version="1.0.0",
        required_ai_governance_version=">=0",
        capabilities=("replay.execute",),
    )

    def validate(self, context) -> None:
        return None

    def register(self, context) -> None:
        context.contributions.replay_execution_adapters(
            (
                ReplayExecutionAdapterContribution(
                    "external-runtime", "v1", _ReplayAdapter()
                ),
            )
        )

    def start(self, context) -> None:
        return None

    def stop(self, context) -> None:
        return None


def test_plugin_can_contribute_a_versioned_replay_adapter() -> None:
    registry = create_plugin_registry(plugins=(_ReplayAdapterPlugin(),))

    contributions = registry.contributions.replay_execution_adapters()

    assert len(contributions) == 1
    assert contributions[0].name == "external-runtime/v1"
    assert contributions[0].adapter.name == "external-runtime/v1"


def test_duplicate_versioned_replay_adapter_contributions_fail_during_startup() -> None:
    class _DuplicatePlugin(_ReplayAdapterPlugin):
        metadata = PluginMetadata(
            name="duplicate-external-runtime-plugin",
            version="1.0.0",
            required_ai_governance_version=">=0",
            capabilities=("replay.execute",),
        )

    with pytest.raises(ExtensionError, match="Duplicate replay_execution_adapters"):
        create_plugin_registry(plugins=(_ReplayAdapterPlugin(), _DuplicatePlugin()))


def test_replay_adapter_contribution_rejects_dynamic_module_like_identifiers() -> None:
    class _UnsafeAdapter:
        name = "untrusted.module/v1"

    with pytest.raises(ValueError, match="lowercase, hyphen-delimited"):
        ReplayExecutionAdapterContribution("untrusted.module", "v1", _UnsafeAdapter())


def test_unsupported_plugin_api_spi_major_fails_explicitly() -> None:
    class _FuturePlugin(_LifecyclePlugin):
        metadata = PluginMetadata(
            name="future-plugin",
            version="1.0.0",
            required_ai_governance_version=">=0",
            spi_version="2",
            contract_version="v2",
        )

    with pytest.raises(ExtensionError, match="Plugin API SPI 2"):
        create_plugin_registry(plugins=(_FuturePlugin(),))
