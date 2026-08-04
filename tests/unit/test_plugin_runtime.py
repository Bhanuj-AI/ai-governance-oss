"""Coverage for plugin lifecycle bootstrap outside the API server."""

from __future__ import annotations

from kavach.plugins import PluginMetadata, create_plugin_registry


class _LifecyclePlugin:
    """Record generic lifecycle calls made by a standalone host."""

    metadata = PluginMetadata(
        name="worker-plugin",
        version="1.0.0",
        required_kavach_version=">=0",
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

    class _EntryPoints:
        def select(self, *, group: str):
            assert group == "kavach.plugins"
            return ()

    monkeypatch.setattr(
        "kavach.plugins.registry.entry_points", lambda: _EntryPoints()
    )
    registry = create_plugin_registry(plugins=(plugin,))
    registry.start()
    registry.stop()

    assert plugin.calls == ["validate", "register", "start", "stop"]
