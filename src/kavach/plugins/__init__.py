"""Stable plugin API for Kavach OSS extensions."""

from kavach.plugins.lifecycle import KavachPlugin
from kavach.plugins.metadata import PluginMetadata, PluginStatus
from kavach.plugins.registry import (
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
from kavach.plugins.registry_types import RouteConflictError
from kavach.plugins.routes import PluginRouteContext, RouteRegistry
from kavach.plugins.contracts import CONTRACT_VERSION, PermissionDefinition, MiddlewareDefinition, JobHandlerDefinition
from kavach.plugins.runtime import (
    DEFAULT_SUPPORTED_EXTENSION_CAPABILITIES,
    create_plugin_registry,
)

__all__ = [
    "DuplicatePluginError", "ExtensionError", "KavachPlugin", "PluginContext",
    "PluginEventContext", "PluginHookContext", "PluginProviderContext",
    "PluginContributionContext", "ContributionRegistry", "CONTRACT_VERSION", "PermissionDefinition", "MiddlewareDefinition", "JobHandlerDefinition",
    "PluginMetadata", "PluginRegistry", "PluginStatus", "ProviderRegistry",
    "ProviderResolutionError", "PluginRouteContext", "RouteConflictError", "RouteRegistry",
    "DEFAULT_SUPPORTED_EXTENSION_CAPABILITIES", "create_plugin_registry",
]
