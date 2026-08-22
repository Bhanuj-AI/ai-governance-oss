"""Plugin lifecycle, provider resolution, and entry-point discovery."""

from __future__ import annotations

import logging
from builtins import Exception, RuntimeError
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Any, TypeVar

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from ai_governance.events import EventPublisher
from ai_governance.hooks import FailurePolicy, HookHandler, HookRegistry
from ai_governance.plugins.contracts import CONTRACT_VERSION, MiddlewareDefinition
from ai_governance.plugins.lifecycle import AIGovernancePlugin
from ai_governance.plugins.metadata import PluginMetadata, PluginStatus
from ai_governance.plugins.routes import PluginRouteContext, RouteRegistry
from ai_governance.version import __version__

T = TypeVar("T")


class ExtensionError(RuntimeError):
    """Base error for an invalid extension declaration or failed lifecycle step.

    The application factory deliberately propagates this error. An extension
    framework must fail deterministically during startup instead of silently
    starting a partially configured enterprise runtime.
    """


class DuplicatePluginError(ExtensionError):
    """Raised when two plugins declare the same immutable metadata name."""


class ProviderResolutionError(ExtensionError):
    """Raised for unresolved providers or an implicit provider replacement."""


@dataclass(frozen=True)
class ProviderRegistration:
    """Inspectable record of a selected SPI provider and its decorator chain.

    The concrete provider object is retained only in process memory and is
    intentionally excluded from diagnostics. ``plugin_name`` remains the
    owner after decoration; ``decorated_by`` records the outer wrappers in the
    order in which they were applied.
    """
    contract: str
    provider: object
    plugin_name: str
    decorated_by: tuple[str, ...] = ()


class ProviderRegistry:
    """Explicit replacement and composition registry for OSS-owned SPIs.

    A contract has exactly one selected provider. Registering a second
    provider requires ``replace=True`` and therefore leaves an auditable,
    intentional ownership change. ``decorate()`` composes behavior around the
    selected provider without changing its contract. The registry does not
    inspect structural ``Protocol`` conformance at runtime; contract test
    suites own that validation.
    """

    def __init__(self) -> None:
        self._providers: dict[type[object], ProviderRegistration] = {}

    def register(
        self,
        contract: type[T],
        provider: T,
        *,
        plugin_name: str = "core",
        replace: bool = False,
    ) -> None:
        """Select ``provider`` for ``contract`` or explicitly replace it.

        Core registrations may use the default ``plugin_name="core"``. Plugin
        code should use :class:`PluginProviderContext`, which binds ownership
        to the declaring plugin and prevents it from impersonating another
        extension.

        Raises:
            ProviderResolutionError: if a provider already exists and
                ``replace`` is not explicitly requested.
        """
        existing = self._providers.get(contract)
        if existing is not None and not replace:
            raise ProviderResolutionError(
                f"Provider for '{_contract_name(contract)}' already belongs to "
                f"'{existing.plugin_name}'; use replace=True explicitly."
            )
        self._providers[contract] = ProviderRegistration(
            contract=_contract_name(contract), provider=provider, plugin_name=plugin_name
        )

    def resolve(self, contract: type[T]) -> T:
        """Return the currently selected provider for a supported SPI.

        Consumers resolve an SPI at their composition boundary instead of
        importing a concrete implementation. No fallback is applied: a missing
        provider is a wiring error and raises :class:`ProviderResolutionError`.
        """
        try:
            return self._providers[contract].provider  # type: ignore[return-value]
        except KeyError as exc:
            raise ProviderResolutionError(
                f"No provider registered for '{_contract_name(contract)}'."
            ) from exc

    def decorate(
        self,
        contract: type[T],
        decorator: Callable[[T], T],
        *,
        plugin_name: str,
    ) -> None:
        """Replace the selected provider with a composition-based wrapper.

        ``decorator`` receives the current provider and must return another
        implementation of the same contract. This preserves the core's public
        SPI while allowing authorization, metering, ranking, and audit behavior
        to wrap the delegate. Decoration requires a provider to be selected
        first and is recorded in runtime diagnostics.
        """
        current = self._providers.get(contract)
        if current is None:
            raise ProviderResolutionError(
                f"Cannot decorate unresolved provider '{_contract_name(contract)}'."
            )
        self._providers[contract] = ProviderRegistration(
            contract=current.contract,
            provider=decorator(current.provider),  # type: ignore[arg-type]
            plugin_name=current.plugin_name,
            decorated_by=(*current.decorated_by, plugin_name),
        )

    def diagnostics(self) -> list[dict[str, object]]:
        """Return a secret-free snapshot of selected providers and decorators."""
        return [
            {
                "contract": registration.contract,
                "plugin": registration.plugin_name,
                "decorated_by": list(registration.decorated_by),
            }
            for registration in sorted(
                self._providers.values(), key=lambda item: item.contract
            )
        ]


class PluginProviderContext:
    """Plugin-bound provider API; provider ownership cannot be spoofed.

    This is the view exposed as ``context.providers``. It delegates to the
    host registry while always recording the plugin that received this context
    as owner. Plugins may resolve providers to compose decorators, but cannot
    register on behalf of core or another plugin.
    """

    def __init__(self, registry: ProviderRegistry, plugin_name: str) -> None:
        self._registry = registry
        self._plugin_name = plugin_name

    def register(
        self, contract: type[T], provider: T, *, replace: bool = False
    ) -> None:
        """Register this plugin's provider under an OSS-owned contract."""
        self._registry.register(
            contract, provider, plugin_name=self._plugin_name, replace=replace
        )

    def resolve(self, contract: type[T]) -> T:
        """Resolve the provider selected by core and prior registrations."""
        return self._registry.resolve(contract)

    def decorate(self, contract: type[T], decorator: Callable[[T], T]) -> None:
        """Apply this plugin's composition wrapper to the selected provider."""
        self._registry.decorate(contract, decorator, plugin_name=self._plugin_name)


class PluginHookContext:
    """Plugin-bound hook API that captures ownership and execution policy.

    The plugin supplies the workflow name, ordering, timeout, retry count, and
    declared failure policy. Ownership is injected by the context, keeping the
    registry's diagnostics trustworthy.
    """

    def __init__(self, registry: HookRegistry, plugin_name: str) -> None:
        self._registry = registry
        self._plugin_name = plugin_name

    def register(
        self,
        *,
        name: str,
        handler: HookHandler,
        order: int = 100,
        failure_policy: FailurePolicy = FailurePolicy.FAIL_CLOSED,
        timeout_seconds: float | None = None,
        retries: int = 0,
    ) -> None:
        """Register one handler for a named OSS lifecycle interception point."""
        self._registry.register(
            name=name, handler=handler, plugin_name=self._plugin_name, order=order,
            failure_policy=failure_policy, timeout_seconds=timeout_seconds, retries=retries,
        )


class PluginEventContext:
    """Plugin-bound event API that captures subscription ownership and order."""

    def __init__(self, publisher: EventPublisher, plugin_name: str) -> None:
        self._publisher = publisher
        self._plugin_name = plugin_name

    def subscribe(
        self,
        *,
        event_type: type[T],
        handler: Callable[..., Any],
        order: int = 100,
        failure_policy: FailurePolicy = FailurePolicy.ISOLATE_AND_CONTINUE,
    ) -> None:
        """Subscribe this plugin to a versioned event contract.

        Event handlers receive the immutable event published by the producer.
        The default policy isolates a failed asynchronous reaction so it cannot
        destabilize the producer's core workflow.
        """
        self._publisher.subscribe(
            event_type=event_type, handler=handler, plugin_name=self._plugin_name,
            order=order, failure_policy=failure_policy,
        )


@dataclass(frozen=True)
class PluginContext:
    """The complete, plugin-bound public surface handed to lifecycle methods.

    Context intentionally provides only provider, hook, event, and route
    contribution APIs. It does not expose FastAPI, service instances,
    repositories, configuration globals, or another plugin's ownership scope.
    Any tenant-specific work must obtain tenant context from a hook invocation
    or domain event rather than reconstructing it from process state.
    """

    plugin_name: str
    providers: PluginProviderContext
    hooks: PluginHookContext
    events: PluginEventContext
    routes: PluginRouteContext
    contributions: PluginContributionContext

class ContributionRegistry:
    """Generic, deterministic registry for optional plugin contributions."""
    def __init__(self) -> None:
        self._items: dict[str, list[tuple[str, object]]] = {}
    def register(self, kind: str, plugin_name: str, items: Iterable[object]) -> None:
        values = self._items.setdefault(kind, [])
        for item in items:
            identity = _contribution_identity(kind, item)
            if any(_contribution_identity(kind, existing) == identity for _, existing in values):
                raise ExtensionError(f"Duplicate {kind} contribution: {identity}.")
            values.append((plugin_name, item))
    def items(self, kind: str) -> tuple[object, ...]:
        return tuple(item for _, item in self._items.get(kind, ()))
    def diagnostics(self) -> dict[str, int]:
        return {kind: len(items) for kind, items in sorted(self._items.items())}

    def install(self, app: object) -> None:
        """Install application-bound contributions after plugin registration."""
        for item in sorted(self.items("middleware"), key=lambda value: value.priority):
            if not isinstance(item, MiddlewareDefinition):
                raise ExtensionError("Middleware contributions must use MiddlewareDefinition.")
            app.add_middleware(item.middleware)  # type: ignore[attr-defined]
        app.state.plugin_health_contributors = self.items("health")  # type: ignore[attr-defined]
        app.state.plugin_metrics_providers = self.items("metrics")  # type: ignore[attr-defined]
        app.state.plugin_telemetry_exporters = self.items("telemetry_exporters")  # type: ignore[attr-defined]
        app.state.plugin_job_handlers = self.items("job_handlers")  # type: ignore[attr-defined]
        app.state.plugin_authorization_enforcers = self.items("authorization_enforcers")  # type: ignore[attr-defined]
        _install_settings(self.items("settings"))
        _install_permissions(self.items("permissions"))
        _install_job_handlers(self.items("job_handlers"))
        for provider in self.items("metrics"):
            provider.register(getattr(app.state, "plugin_metrics", {}))

    def emit(self, name: str, attributes: dict[str, object]) -> None:
        from ai_governance.plugins.contracts import TelemetryEvent
        event = TelemetryEvent(name, dict(attributes))
        for exporter in self.items("telemetry_exporters"):
            try:
                exporter(event)
            except Exception:
                logging.getLogger("ai_governance.extensions").exception("plugin_exporter_failed")

class PluginContributionContext:
    def __init__(self, registry: ContributionRegistry, plugin_name: str) -> None:
        self._registry, self._plugin_name = registry, plugin_name
    def permissions(self, items: Iterable[object]) -> None: self._registry.register("permissions", self._plugin_name, items)
    def middleware(self, items: Iterable[object]) -> None: self._registry.register("middleware", self._plugin_name, items)
    def settings(self, items: Iterable[object]) -> None: self._registry.register("settings", self._plugin_name, items)
    def job_handlers(self, items: Iterable[object]) -> None: self._registry.register("job_handlers", self._plugin_name, items)
    def telemetry_exporters(self, items: Iterable[object]) -> None: self._registry.register("telemetry_exporters", self._plugin_name, items)
    def health(self, items: Iterable[object]) -> None: self._registry.register("health", self._plugin_name, items)
    def metrics(self, items: Iterable[object]) -> None: self._registry.register("metrics", self._plugin_name, items)
    def authorization_enforcers(self, items: Iterable[object]) -> None: self._registry.register("authorization_enforcers", self._plugin_name, items)


@dataclass
class _PluginRecord:
    plugin: AIGovernancePlugin
    metadata: PluginMetadata
    status: PluginStatus = PluginStatus.DISCOVERED
    failure_reason: str | None = None


class PluginRegistry:
    """Own deterministic extension discovery, validation, and lifecycle state.

    The registry is created by the AI Governance Control Plane application factory. It discovers
    installed entry points, validates every plugin before registration, then
    starts registered plugins in declaration order. Shutdown is intentionally
    reverse order. A registration or startup failure is fatal: this avoids
    ambiguous partial capability ownership. Diagnostics contain identities and
    outcomes, but never provider objects or plugin configuration secrets.
    """

    def __init__(
        self,
        *,
        supported_capabilities: Iterable[str] = (),
        ai_governance_version: str = __version__,
    ) -> None:
        """Create an isolated runtime registry for one AI Governance Control Plane process.

        Args:
            supported_capabilities: OSS allow-list that plugin metadata is
                checked against before any plugin callback executes.
            ai_governance_version: Version used for compatibility checks. Tests and
                embedders may provide it explicitly; production uses package
                metadata.
        """
        self.providers = ProviderRegistry()
        self.hooks = HookRegistry()
        self.events = EventPublisher()
        self.routes = RouteRegistry()
        self.contributions = ContributionRegistry()
        self._supported_capabilities = frozenset(supported_capabilities)
        self._ai_governance_version = ai_governance_version
        self._records: dict[str, _PluginRecord] = {}

    def register(self, plugin: AIGovernancePlugin) -> None:
        """Record a programmatically supplied plugin in deterministic order.

        This method does not execute plugin code. Call :meth:`initialize` once
        all programmatic and entry-point plugins have been registered.
        """
        metadata = plugin.metadata
        if metadata.name in self._records:
            raise DuplicatePluginError(f"Plugin '{metadata.name}' is already registered.")
        self._records[metadata.name] = _PluginRecord(plugin=plugin, metadata=metadata)

    def discover(self, group: str = "ai_governance.plugins") -> None:
        """Load plugins from a Python packaging entry-point group.

        Each entry point must resolve to a plugin instance or a zero-argument
        plugin class. Discovery is deliberately explicit and generic; OSS does
        not import, name, or conditionally detect an enterprise distribution.
        """
        selected = entry_points().select(group=group)
        for entry_point in sorted(selected, key=lambda item: item.name):
            self._register_entry_point(entry_point)

    def initialize(self) -> None:
        """Validate and register every discovered plugin before app startup.

        Compatibility, capability, and plugin-defined validation run before
        ``plugin.register()``. A failure is wrapped as :class:`ExtensionError`
        and aborts remaining initialization, ensuring duplicate routes and
        provider claims never reach a running application.
        """
        for record in self._records.values():
            context = self._context(record.metadata.name)
            try:
                self._validate(record, context)
                record.plugin.register(context)
                record.status = PluginStatus.REGISTERED
            except Exception as exc:
                if record.status != PluginStatus.INCOMPATIBLE:
                    record.status = PluginStatus.FAILED
                record.failure_reason = str(exc)
                raise ExtensionError(
                    f"Plugin '{record.metadata.name}' failed registration: {exc}"
                ) from exc

    def start(self) -> None:
        """Start registered plugins in registration order during app lifespan.

        A startup failure marks the offending plugin failed and aborts startup;
        already-started plugin teardown is handled by the application lifespan.
        """
        for record in self._records.values():
            if record.status != PluginStatus.REGISTERED:
                continue
            try:
                record.plugin.start(self._context(record.metadata.name))
                record.status = PluginStatus.ACTIVE
            except Exception as exc:
                record.status = PluginStatus.FAILED
                record.failure_reason = str(exc)
                raise ExtensionError(
                    f"Plugin '{record.metadata.name}' failed startup: {exc}"
                ) from exc

    def stop(self) -> None:
        """Stop active plugins in reverse order without masking shutdown.

        Plugin shutdown is best effort. Errors are logged with plugin identity
        and the registry continues, so one extension cannot prevent worker or
        host process cleanup.
        """
        for record in reversed(tuple(self._records.values())):
            if record.status != PluginStatus.ACTIVE:
                continue
            try:
                record.plugin.stop(self._context(record.metadata.name))
            except Exception:
                logging.getLogger("ai_governance.extensions").exception(
                    "plugin_stop_failed", extra={"plugin": record.metadata.name}
                )

    def diagnostics(self) -> dict[str, object]:
        """Build the secret-free runtime snapshot used by the admin endpoint."""
        return {
            "ai_governance_version": self._ai_governance_version,
            "plugins": [
                {
                    **asdict(record.metadata),
                    "capabilities": list(record.metadata.capabilities),
                    "status": record.status.value,
                    "failure_reason": record.failure_reason,
                }
                for record in self._records.values()
            ],
            "providers": self.providers.diagnostics(),
            "hooks": self.hooks.diagnostics(),
            "events": self.events.diagnostics(),
            "routes": self.routes.diagnostics(),
            "contributions": self.contributions.diagnostics(),
            "contract_version": CONTRACT_VERSION,
        }

    def _validate(self, record: _PluginRecord, context: PluginContext) -> None:
        try:
            compatible = Version(self._ai_governance_version) in SpecifierSet(
                record.metadata.required_ai_governance_version
            )
        except Exception as exc:
            raise ExtensionError(
                f"Plugin '{record.metadata.name}' declares an invalid version range."
            ) from exc
        if not compatible:
            record.status = PluginStatus.INCOMPATIBLE
            raise ExtensionError(
                f"Plugin '{record.metadata.name}' requires AI Governance Control Plane "
                f"{record.metadata.required_ai_governance_version}, running {self._ai_governance_version}."
            )
        unsupported = set(record.metadata.capabilities) - self._supported_capabilities
        if unsupported:
            raise ExtensionError(
                f"Plugin '{record.metadata.name}' requests unsupported capabilities: "
                f"{', '.join(sorted(unsupported))}."
            )
        record.plugin.validate(context)

    def _context(self, plugin_name: str) -> PluginContext:
        return PluginContext(
            plugin_name=plugin_name,
            providers=PluginProviderContext(self.providers, plugin_name),
            hooks=PluginHookContext(self.hooks, plugin_name),
            events=PluginEventContext(self.events, plugin_name),
            routes=PluginRouteContext(self.routes, plugin_name),
            contributions=PluginContributionContext(self.contributions, plugin_name),
        )

    def _register_entry_point(self, entry_point: EntryPoint) -> None:
        try:
            loaded: Any = entry_point.load()
            plugin = loaded() if isinstance(loaded, type) else loaded
            self.register(plugin)
        except Exception as exc:
            raise ExtensionError(
                f"Could not load plugin entry point '{entry_point.name}': {exc}"
            ) from exc


def _contract_name(contract: type[object]) -> str:
    return f"{contract.__module__}.{contract.__qualname__}"

def _contribution_identity(kind: str, item: object) -> str:
    if kind == "middleware":
        return f"{item.middleware.__module__}.{item.middleware.__qualname__}"  # type: ignore[attr-defined]
    if kind == "settings":
        return str(item.key)  # type: ignore[attr-defined]
    if kind == "permissions":
        return str(item.name)  # type: ignore[attr-defined]
    if kind == "job_handlers":
        return str(item.job_type)  # type: ignore[attr-defined]
    if kind == "health":
        return str(item.name())  # type: ignore[attr-defined]
    return f"{type(item).__module__}.{type(item).__qualname__}"

def _install_settings(items: tuple[object, ...]) -> None:
    if not items:
        return
    from ai_governance.settings_control.registry import register_extension_definitions
    register_extension_definitions(items)

def _install_permissions(items: tuple[object, ...]) -> None:
    if items:
        from ai_governance.tenancy.permissions import register_extension_permissions
        register_extension_permissions(items)

def _install_job_handlers(items: tuple[object, ...]) -> None:
    if items:
        from ai_governance.services.job_executor import register_extension_handlers
        register_extension_handlers(items)
