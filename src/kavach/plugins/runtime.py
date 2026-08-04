"""Generic bootstrap helpers for plugin-enabled Kavach processes."""

from __future__ import annotations

from collections.abc import Iterable

from kavach.plugins.lifecycle import KavachPlugin
from kavach.plugins.registry import PluginRegistry


DEFAULT_SUPPORTED_EXTENSION_CAPABILITIES = frozenset(
    {
        "audit.write",
        "evaluation.execute",
        "identity.resolve",
        "jobs.submit",
        "notification.send",
        "ontology.write",
        "policy.evaluate",
        "search.read",
        "settings.read",
    }
)


def create_plugin_registry(
    *,
    plugins: Iterable[KavachPlugin] = (),
    supported_capabilities: Iterable[str] = DEFAULT_SUPPORTED_EXTENSION_CAPABILITIES,
) -> PluginRegistry:
    """Discover and register extensions for any Kavach runtime host.

    API servers and standalone workers share this bootstrap so a plugin's
    generic providers, hooks, and event subscribers have the same lifecycle
    regardless of which process performs the work.
    """
    registry = PluginRegistry(supported_capabilities=supported_capabilities)
    registry.discover()
    for plugin in plugins:
        registry.register(plugin)
    registry.initialize()
    return registry
