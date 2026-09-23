"""Versioned, generic extension contracts owned by the AI Governance Control Plane plugin API."""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Protocol

from ai_governance.authorization.contracts import AuthorizationEnforcer
from ai_governance.spi.replay import ReplayExecutionAdapter

CONTRACT_VERSION = "v1"
_REPLAY_ADAPTER_COMPONENT = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


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
class ReplayExecutionAdapterContribution:
    """One versioned external Replay adapter contributed by a plugin.

    The canonical identity is ``{adapter_id}/{adapter_version}``, for example
    ``example-runtime/v1``.  This binds plugin metadata to the adapter's
    persisted Replay configuration name and makes collisions fail at startup.
    """

    adapter_id: str
    adapter_version: str
    adapter: ReplayExecutionAdapter

    def __post_init__(self) -> None:
        if not _REPLAY_ADAPTER_COMPONENT.fullmatch(
            self.adapter_id
        ) or not _REPLAY_ADAPTER_COMPONENT.fullmatch(self.adapter_version):
            raise ValueError(
                "Replay adapter contribution requires lowercase, hyphen-delimited adapter ID and version."
            )
        if self.adapter.name != self.name:
            raise ValueError(
                "Replay adapter contribution identity must match adapter.name."
            )

    @property
    def name(self) -> str:
        return f"{self.adapter_id}/{self.adapter_version}"


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
