"""Versioned, generic extension contracts owned by the AI Governance Control Plane plugin API."""
from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Protocol

from ai_governance.authorization.contracts import AuthorizationEnforcer

CONTRACT_VERSION = "v1"

@dataclass(frozen=True)
class PermissionDefinition:
    name: str
    description: str = ""
    granted_to_administrators: bool = True

@dataclass(frozen=True)
class MiddlewareDefinition:
    middleware: type[object]
    priority: int = 100

@dataclass(frozen=True)
class JobHandlerDefinition:
    job_type: object
    handler: object
    operation: str | None = None

@dataclass(frozen=True)
class TelemetryEvent:
    name: str
    attributes: Mapping[str, object]

class PermissionProvider(Protocol):
    def permissions(self) -> Collection[PermissionDefinition]: ...
class ApplicationMiddlewareProvider(Protocol):
    def middlewares(self) -> Collection[MiddlewareDefinition]: ...
class SettingsProvider(Protocol):
    def settings(self) -> Collection[object]: ...
class JobHandlerProvider(Protocol):
    def handlers(self) -> Collection[JobHandlerDefinition]: ...
class TelemetryExporterProvider(Protocol):
    def exporters(self) -> Collection[Callable[[TelemetryEvent], None]]: ...
class HealthContributor(Protocol):
    def name(self) -> str: ...
    def health(self) -> Mapping[str, object]: ...
class MetricsProvider(Protocol):
    def register(self, registry: object) -> None: ...
class AuthorizationEnforcerProvider(Protocol):
    def authorization_enforcers(self) -> Collection[AuthorizationEnforcer]: ...
