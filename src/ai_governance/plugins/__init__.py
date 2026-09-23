"""Stable plugin API for AI Governance Control Plane OSS extensions."""

from ai_governance.plugins.contracts import (
    CONTRACT_VERSION,
    JobHandlerDefinition,
    MiddlewareDefinition,
    PermissionDefinition,
    ReplayExecutionAdapterContribution,
)
from ai_governance.plugins.lifecycle import AIGovernancePlugin
from ai_governance.plugins.metadata import PluginMetadata, PluginStatus
from ai_governance.plugins.registry import (
    ContributionRegistry,
    DuplicatePluginError,
    ExtensionError,
    PluginContext,
    PluginContributionContext,
    PluginEventContext,
    PluginHookContext,
    PluginProviderContext,
    PluginRegistry,
    ProviderRegistry,
    ProviderResolutionError,
)
from ai_governance.plugins.registry_types import RouteConflictError
from ai_governance.plugins.routes import PluginRouteContext, RouteRegistry
from ai_governance.plugins.runtime import (
    DEFAULT_SUPPORTED_EXTENSION_CAPABILITIES,
    create_plugin_registry,
)

__all__ = [
    "CONTRACT_VERSION",
    "DEFAULT_SUPPORTED_EXTENSION_CAPABILITIES",
    "AIGovernancePlugin",
    "ContributionRegistry",
    "DuplicatePluginError",
    "ExtensionError",
    "JobHandlerDefinition",
    "MiddlewareDefinition",
    "PermissionDefinition",
    "PluginContext",
    "PluginContributionContext",
    "PluginEventContext",
    "PluginHookContext",
    "PluginMetadata",
    "PluginProviderContext",
    "PluginRegistry",
    "PluginRouteContext",
    "PluginStatus",
    "ProviderRegistry",
    "ProviderResolutionError",
    "ReplayExecutionAdapterContribution",
    "RouteConflictError",
    "RouteRegistry",
    "create_plugin_registry",
]
