"""Controlled REST route contributions from registered plugins."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from ai_governance.plugins.registry_types import RouteConflictError


@dataclass(frozen=True)
class RouteContribution:
    """One deferred REST endpoint claim made by a named plugin.

    Contributions are collected before they are attached to FastAPI. Keeping
    them as immutable values lets the host reject collisions before serving a
    request and report the responsible plugin in runtime diagnostics.
    """
    method: str
    path: str
    handler: Callable[..., Any]
    plugin_name: str
    replace: bool = False
    kwargs: dict[str, Any] = field(default_factory=dict)


class RouteRegistry:
    """Collect route contributions and install only an unambiguous route table.

    Normal additions cannot claim an existing core or plugin method/path pair.
    A replacement has two gates: OSS must first call
    :meth:`authorize_replacement`, and the plugin must explicitly call
    ``replace()``. This makes an API override a deliberate versioned contract,
    rather than a side effect of import order.
    """

    def __init__(self) -> None:
        self._contributions: dict[tuple[str, str], RouteContribution] = {}
        self._replaceable: set[tuple[str, str]] = set()

    def authorize_replacement(self, *, method: str, path: str) -> None:
        """Declare an OSS route as an intentionally replaceable SPI point.

        Only OSS composition code should call this method. Plugins receive the
        narrower :class:`PluginRouteContext`, which exposes ``replace`` but
        cannot authorize a new replacement point for itself.
        """
        self._replaceable.add(_key(method, path))

    def add(
        self, *, method: str, path: str, handler: Callable[..., Any], plugin_name: str,
        **kwargs: Any,
    ) -> None:
        """Claim a new route not owned by core or another plugin.

        ``kwargs`` are passed through to :meth:`FastAPI.add_api_route` during
        installation and can contain response models, tags, dependencies, and
        OpenAPI metadata. Conflict detection uses the normalized method/path
        pair, not handler identity.
        """
        self._claim(RouteContribution(method.upper(), path, handler, plugin_name, kwargs=kwargs))

    def replace(
        self, *, method: str, path: str, handler: Callable[..., Any], plugin_name: str,
        **kwargs: Any,
    ) -> None:
        """Claim an OSS-authorized route replacement.

        Raises:
            RouteConflictError: if core has not explicitly authorized this
                method/path as a replacement contract, or another plugin has
                already claimed it.
        """
        key = _key(method, path)
        if key not in self._replaceable:
            raise RouteConflictError(
                f"Route {method.upper()} {path} is not an authorized replacement point."
            )
        self._claim(RouteContribution(method.upper(), path, handler, plugin_name, True, kwargs))

    def install(self, app: FastAPI) -> None:
        """Validate contributions against core routes and attach them to FastAPI.

        The host invokes this only after all core routers are attached. For an
        authorized replacement, the matching FastAPI route is removed before
        the new handler is registered; additions leave all existing routes
        untouched. Any accidental collision fails startup rather than creating
        framework-dependent routing precedence.
        """
        existing = {
            (method, route.path)
            for route in app.router.routes
            if isinstance(route, APIRoute)
            for method in route.methods or set()
        }
        for key, contribution in self._contributions.items():
            if key in existing and not contribution.replace:
                raise RouteConflictError(
                    f"Route {contribution.method} {contribution.path} already exists."
                )
            if contribution.replace:
                app.router.routes[:] = [
                    route
                    for route in app.router.routes
                    if not (
                        isinstance(route, APIRoute)
                        and route.path == contribution.path
                        and contribution.method in (route.methods or set())
                    )
                ]
            app.add_api_route(
                contribution.path,
                contribution.handler,
                methods=[contribution.method],
                **contribution.kwargs,
            )
            existing.add(key)

    def diagnostics(self) -> list[dict[str, object]]:
        """Return route ownership and replacement state without handler objects."""
        return [
            {"method": item.method, "path": item.path, "plugin": item.plugin_name,
             "replace": item.replace}
            for item in self._contributions.values()
        ]

    def _claim(self, contribution: RouteContribution) -> None:
        """Store one unique deferred claim or identify its existing owner."""
        key = _key(contribution.method, contribution.path)
        if key in self._contributions:
            owner = self._contributions[key].plugin_name
            raise RouteConflictError(
                f"Route {contribution.method} {contribution.path} is already claimed by '{owner}'."
            )
        self._contributions[key] = contribution


def _key(method: str, path: str) -> tuple[str, str]:
    """Canonicalize a route identity for conflict and authorization lookup."""
    return method.upper(), path


class PluginRouteContext:
    """Plugin-bound route view that records ownership automatically.

    The context intentionally omits replacement authorization. A plugin can
    request an existing OSS replacement point, but cannot expand the set of
    replaceable endpoints without a core release.
    """

    def __init__(self, registry: RouteRegistry, plugin_name: str) -> None:
        self._registry = registry
        self._plugin_name = plugin_name

    def add(
        self, *, method: str, path: str, handler: Callable[..., Any], **kwargs: Any
    ) -> None:
        """Add a route attributed to the plugin that received this context."""
        self._registry.add(
            method=method, path=path, handler=handler, plugin_name=self._plugin_name,
            **kwargs,
        )

    def replace(
        self, *, method: str, path: str, handler: Callable[..., Any], **kwargs: Any
    ) -> None:
        """Request an explicitly authorized OSS route replacement."""
        self._registry.replace(
            method=method, path=path, handler=handler, plugin_name=self._plugin_name,
            **kwargs,
        )
