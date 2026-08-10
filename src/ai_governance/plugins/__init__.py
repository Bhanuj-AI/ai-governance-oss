"""Stable plugin API for AI Governance Control Plane OSS extensions."""

from ai_governance.plugins.lifecycle import AIGovernancePlugin
from ai_governance.plugins.metadata import PluginMetadata, PluginStatus
from ai_governance.plugins.registry import (
    DuplicatePluginError,
    ExtensionError,
    PluginEventContext,
    PluginHookContext,
    PluginContext,
    PluginContributionContext,
    ContributionRegistry,
    PluginProviderContext,
    PluginRegistry,
    ProviderRegistry,
    ProviderResolutionError,
)
from ai_governance.plugins.registry_types import RouteConflictError
from ai_governance.plugins.routes import PluginRouteContext, RouteRegistry
from ai_governance.plugins.contracts import CONTRACT_VERSION, PermissionDefinition, MiddlewareDefinition, JobHandlerDefinition
from ai_governance.plugins.runtime import (
    DEFAULT_SUPPORTED_EXTENSION_CAPABILITIES,
    create_plugin_registry,
)

__all__ = [
    "DuplicatePluginError", "ExtensionError", "AIGovernancePlugin", "PluginContext",
    "PluginEventContext", "PluginHookContext", "PluginProviderContext",
    "PluginContributionContext", "ContributionRegistry", "CONTRACT_VERSION", "PermissionDefinition", "MiddlewareDefinition", "JobHandlerDefinition",
    "PluginMetadata", "PluginRegistry", "PluginStatus", "ProviderRegistry",
    "ProviderResolutionError", "PluginRouteContext", "RouteConflictError", "RouteRegistry",
    "DEFAULT_SUPPORTED_EXTENSION_CAPABILITIES", "create_plugin_registry",
]
