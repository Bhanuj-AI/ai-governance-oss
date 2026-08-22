"""Public entry-point contract for optional MCP tool packages."""

from __future__ import annotations

from builtins import RuntimeError
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any, Protocol, TypeVar, cast

from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pydantic import BaseModel

from ai_governance.mcp.clients import RestClient, RestClientError
from ai_governance.mcp.mappers import MCPResponseMapper
from ai_governance.mcp.observability import MCPMetrics
from ai_governance.mcp.registry import ToolRegistry
from ai_governance.version import __version__

MCP_TOOL_PLUGIN_ENTRY_POINT_GROUP = "ai_governance.mcp.plugins"
RequestModel = TypeVar("RequestModel", bound=BaseModel)


class MCPToolPluginError(RuntimeError):
    """Raised when an MCP tool plugin cannot be discovered or registered."""


@dataclass(frozen=True)
class MCPToolPluginMetadata:
    """Immutable compatibility declaration for an MCP tool plugin."""

    name: str
    version: str
    required_ai_governance_version: str

    def __post_init__(self) -> None:
        name, version, required_ai_governance_version = (
            self.name,
            self.version,
            self.required_ai_governance_version,
        )
        if not name.strip() or not version.strip() or not required_ai_governance_version.strip():
            raise ValueError(
                "MCP tool plugin metadata requires name, version, and AI Governance Control Plane version range."
            )


class MCPToolPlugin(Protocol):
    """Stable contract implemented by packages contributing MCP tools."""

    @property
    def metadata(self) -> MCPToolPluginMetadata:
        """Return immutable identity and OSS compatibility metadata."""
        ...

    def register(self, context: MCPToolPluginContext) -> None:
        """Register tools through the supplied context during server startup."""
        ...


class MCPToolPluginContext:
    """MCP extension surface for registering REST-backed tool adapters."""

    def __init__(
        self,
        registry: ToolRegistry,
        rest_client: RestClient,
        metrics: MCPMetrics,
    ) -> None:
        self._registry = registry
        self._rest_client = rest_client
        self._metrics = metrics

    def register_tool(
        self,
        *,
        name: str,
        description: str,
        request_model: type[RequestModel],
        handler: Callable[[RequestModel], Any],
    ) -> None:
        """Register one public MCP tool; duplicate names fail server startup."""
        self._registry.register(
            name=name,
            description=description,
            request_model=request_model,
            # The registry executes the handler only after parsing this exact
            # request model. Preserve that relationship for plugin type checkers
            # while adapting to the registry's non-generic internal contract.
            handler=cast(Callable[[BaseModel], Any], handler),
        )

    def get(
        self,
        *,
        organization_id: str,
        project_id: str | None,
        path: str,
        query: Mapping[str, Any] | None = None,
    ) -> Any:
        """Call a tenant-scoped REST GET and map its public response."""
        return self._request(
            "GET",
            organization_id=organization_id,
            project_id=project_id,
            path=path,
            query=query,
        )

    def post(
        self,
        *,
        organization_id: str,
        project_id: str | None,
        path: str,
        body: Mapping[str, Any],
    ) -> Any:
        """Call a tenant-scoped REST POST and map its public response."""
        return self._request(
            "POST",
            organization_id=organization_id,
            project_id=project_id,
            path=path,
            body=body,
        )

    def patch(
        self,
        *,
        organization_id: str,
        project_id: str | None,
        path: str,
        body: Mapping[str, Any],
    ) -> Any:
        """Call a tenant-scoped REST PATCH and map its public response."""
        return self._request(
            "PATCH",
            organization_id=organization_id,
            project_id=project_id,
            path=path,
            body=body,
        )

    def _request(
        self,
        method: str,
        *,
        organization_id: str,
        project_id: str | None,
        path: str,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        client = self._rest_client.with_tenant_context(organization_id, project_id)
        self._metrics.record_rest_call()
        try:
            response = client.request(method, path, query=query, body=body)
            return MCPResponseMapper.from_rest_payload(response)
        except RestClientError:
            self._metrics.record_rest_failure()
            raise


class MCPToolPluginRegistry:
    """Discover and register compatible MCP tool plugins deterministically."""

    def __init__(self, *, ai_governance_version: str = __version__) -> None:
        self._ai_governance_version = ai_governance_version
        self._plugins: dict[str, MCPToolPlugin] = {}

    def discover(self) -> None:
        """Load plugins published through the ``ai_governance.mcp.plugins`` group."""
        for entry_point in sorted(
            entry_points().select(group=MCP_TOOL_PLUGIN_ENTRY_POINT_GROUP),
            key=lambda item: item.name,
        ):
            try:
                plugin = entry_point.load()
                if isinstance(plugin, type):
                    plugin = plugin()
                self.register(plugin)
            except MCPToolPluginError:
                raise
            except Exception as exc:
                raise MCPToolPluginError(
                    f"MCP tool plugin '{entry_point.name}' could not be loaded: {exc}"
                ) from exc

    def register(self, plugin: MCPToolPlugin) -> None:
        """Register a programmatically supplied plugin for this server."""
        metadata = plugin.metadata
        if not isinstance(metadata, MCPToolPluginMetadata):
            raise MCPToolPluginError(
                "MCP tool plugins must expose MCPToolPluginMetadata."
            )
        if metadata.name in self._plugins:
            raise MCPToolPluginError(
                f"MCP tool plugin '{metadata.name}' is already registered."
            )
        self._plugins[metadata.name] = plugin

    def initialize(
        self,
        registry: ToolRegistry,
        rest_client: RestClient,
        metrics: MCPMetrics,
    ) -> None:
        """Validate compatibility and install all declared tools."""
        context = MCPToolPluginContext(registry, rest_client, metrics)
        for plugin in self._plugins.values():
            metadata = plugin.metadata
            try:
                compatible = Version(self._ai_governance_version) in SpecifierSet(
                    metadata.required_ai_governance_version
                )
            except Exception as exc:
                raise MCPToolPluginError(
                    f"MCP tool plugin '{metadata.name}' has an invalid AI Governance Control Plane version range."
                ) from exc
            if not compatible:
                raise MCPToolPluginError(
                    f"MCP tool plugin '{metadata.name}' requires AI Governance Control Plane "
                    f"{metadata.required_ai_governance_version}, but running version is "
                    f"{self._ai_governance_version}."
                )
            try:
                plugin.register(context)
            except Exception as exc:
                raise MCPToolPluginError(
                    f"MCP tool plugin '{metadata.name}' failed registration: {exc}"
                ) from exc


def initialize_mcp_tool_plugins(
    registry: ToolRegistry,
    rest_client: RestClient,
    metrics: MCPMetrics,
    plugins: Iterable[MCPToolPlugin] = (),
) -> None:
    """Discover installed packages and register optional programmatic plugins."""
    plugin_registry = MCPToolPluginRegistry()
    plugin_registry.discover()
    for plugin in plugins:
        plugin_registry.register(plugin)
    plugin_registry.initialize(registry, rest_client, metrics)
