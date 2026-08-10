from __future__ import annotations

import asyncio
from importlib.metadata import EntryPoint

import pytest
from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.events import EvaluationCompleted
from ai_governance.hooks import FailurePolicy, HookInvocation
from ai_governance.plugins import (
    ExtensionError,
    PluginMetadata,
    PluginRegistry,
    PluginStatus,
    ProviderRegistry,
    ProviderResolutionError,
    RouteConflictError,
)


class _RoutePlugin:
    metadata = PluginMetadata(
        name="route-plugin",
        version="1.0.0",
        required_ai_governance_version=">=0",
        capabilities=("search.read",),
    )

    def __init__(self) -> None:
        self.lifecycle: list[str] = []

    def validate(self, context) -> None:
        self.lifecycle.append("validate")

    def register(self, context) -> None:
        context.routes.add(
            method="GET",
            path="/api/v1/enterprise/example",
            handler=lambda: {"source": "plugin"},
        )

    def start(self, context) -> None:
        self.lifecycle.append("start")

    def stop(self, context) -> None:
        self.lifecycle.append("stop")


class _IncompatiblePlugin(_RoutePlugin):
    metadata = PluginMetadata(
        name="incompatible-plugin",
        version="1.0.0",
        required_ai_governance_version=">=9",
    )


def test_plugin_route_lifecycle_and_runtime_diagnostics() -> None:
    plugin = _RoutePlugin()
    with TestClient(create_app(plugins=[plugin])) as client:
        assert client.get("/api/v1/enterprise/example").json() == {"source": "plugin"}
        diagnostics = client.get("/api/v1/runtime/extensions").json()

    assert plugin.lifecycle == ["validate", "start", "stop"]
    assert diagnostics["plugins"] == [
        {
            "name": "route-plugin",
            "version": "1.0.0",
            "required_ai_governance_version": ">=0",
            "capabilities": ["search.read"],
            "contract_version": "v1",
            "status": "active",
            "failure_reason": None,
        }
    ]
    assert diagnostics["routes"] == [
        {
            "method": "GET",
            "path": "/api/v1/enterprise/example",
            "plugin": "route-plugin",
            "replace": False,
        }
    ]


def test_provider_replacement_and_decoration_are_explicit() -> None:
    class Contract:
        pass

    providers = ProviderRegistry()
    providers.register(Contract, "oss", plugin_name="core")
    with pytest.raises(ProviderResolutionError, match="replace=True"):
        providers.register(Contract, "enterprise", plugin_name="enterprise")

    providers.register(Contract, "enterprise", plugin_name="enterprise", replace=True)
    providers.decorate(Contract, lambda value: f"governed-{value}", plugin_name="audit")

    assert providers.resolve(Contract) == "governed-enterprise"
    assert providers.diagnostics() == [
        {
            "contract": f"{__name__}.test_provider_replacement_and_decoration_are_explicit.<locals>.Contract",
            "plugin": "enterprise",
            "decorated_by": ["audit"],
        }
    ]


def test_hooks_and_events_have_deterministic_order_and_immutable_context() -> None:
    registry = PluginRegistry(ai_governance_version="1.2.4")
    hook_order: list[str] = []
    registry.hooks.register(
        name="after_execution",
        plugin_name="later",
        order=20,
        handler=lambda invocation: hook_order.append("later"),
    )
    registry.hooks.register(
        name="after_execution",
        plugin_name="first",
        order=10,
        handler=lambda invocation: hook_order.append("first"),
    )
    invocation = HookInvocation(
        name="after_execution", payload={"id": "1"}, tenant={"project_id": "project"}
    )
    with pytest.raises(TypeError):
        invocation.payload["id"] = "2"  # type: ignore[index]

    executions = asyncio.run(registry.hooks.invoke(invocation))
    assert hook_order == ["first", "later"]
    assert [item.order for item in executions] == [10, 20]

    event_order: list[str] = []
    registry.events.subscribe(
        event_type=EvaluationCompleted,
        plugin_name="first",
        order=10,
        failure_policy=FailurePolicy.FAIL_CLOSED,
        handler=lambda event: event_order.append("first"),
    )
    registry.events.subscribe(
        event_type=EvaluationCompleted,
        plugin_name="later",
        order=20,
        handler=lambda event: event_order.append("later"),
    )
    event = EvaluationCompleted(
        evaluation_id="evaluation-1", result={"score": 1}, tenant={"project_id": "project"}
    )
    asyncio.run(registry.events.publish(event))
    assert event_order == ["first", "later"]
    with pytest.raises(TypeError):
        event.result["score"] = 2  # type: ignore[index]


def test_plugin_compatibility_capabilities_and_route_conflicts_fail_fast() -> None:
    plugin = _RoutePlugin()
    registry = PluginRegistry(
        supported_capabilities=(), ai_governance_version="1.2.4"
    )
    registry.register(plugin)
    with pytest.raises(ExtensionError, match="unsupported capabilities"):
        registry.initialize()

    incompatible = PluginRegistry(
        supported_capabilities={"search.read"}, ai_governance_version="1.2.4"
    )
    incompatible.register(_IncompatiblePlugin())
    with pytest.raises(ExtensionError, match="requires AI Governance Control Plane"):
        incompatible.initialize()
    assert incompatible.diagnostics()["plugins"][0]["status"] == PluginStatus.INCOMPATIBLE.value

    routes = PluginRegistry().routes
    routes.add(method="GET", path="/same", handler=lambda: None, plugin_name="one")
    with pytest.raises(RouteConflictError, match="already claimed"):
        routes.add(method="GET", path="/same", handler=lambda: None, plugin_name="two")
    with pytest.raises(RouteConflictError, match="not an authorized"):
        routes.replace(method="GET", path="/same", handler=lambda: None, plugin_name="one")


def test_plugin_is_discovered_through_the_packaging_entry_point(monkeypatch) -> None:
    """Exercise the same entry-point load path used by an installed extension."""

    entry_point = EntryPoint(
        name="route-plugin",
        value="tests.unit.test_extension_framework:_RoutePlugin",
        group="ai_governance.plugins",
    )

    class _EntryPoints:
        def select(self, *, group: str):
            assert group == "ai_governance.plugins"
            return (entry_point,)

    monkeypatch.setattr("ai_governance.plugins.registry.entry_points", lambda: _EntryPoints())
    registry = PluginRegistry(
        supported_capabilities={"search.read"}, ai_governance_version="1.2.4"
    )

    registry.discover()
    registry.initialize()

    assert registry.diagnostics()["plugins"][0]["name"] == "route-plugin"
    assert registry.diagnostics()["routes"][0]["path"] == "/api/v1/enterprise/example"
