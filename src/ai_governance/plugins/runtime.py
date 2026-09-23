"""Generic bootstrap helpers for plugin-enabled AI Governance Control Plane processes."""

from __future__ import annotations

from collections.abc import Iterable

from ai_governance.plugins.lifecycle import AIGovernancePlugin
from ai_governance.plugins.registry import PluginRegistry

DEFAULT_SUPPORTED_EXTENSION_CAPABILITIES = frozenset(
    {
        "audit.write",
        "evaluation.execute",
        "identity.resolve",
        "jobs.submit",
        "notification.send",
        "ontology.write",
        "policy.evaluate",
        "replay.execute",
        "search.read",
        "settings.read",
    }
)


def create_plugin_registry(
    *,
    plugins: Iterable[AIGovernancePlugin] = (),
    supported_capabilities: Iterable[str] = DEFAULT_SUPPORTED_EXTENSION_CAPABILITIES,
) -> PluginRegistry:
    """Discover and register extensions for any AI Governance Control Plane runtime host.

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
