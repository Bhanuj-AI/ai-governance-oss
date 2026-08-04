"""Versioned identity and state for Kavach extensions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PluginStatus(StrEnum):
    """Lifecycle state reported for a discovered extension.

    ``INCOMPATIBLE`` means the plugin's declared Kavach version range could
    not be satisfied. ``FAILED`` records an otherwise compatible plugin whose
    validation, registration, or startup callback raised an exception.
    """
    DISCOVERED = "discovered"
    REGISTERED = "registered"
    ACTIVE = "active"
    DISABLED = "disabled"
    FAILED = "failed"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class PluginMetadata:
    """Immutable identity, compatibility, and permission declaration.

    ``required_kavach_version`` is a :mod:`packaging` specifier set, such as
    ``">=1.4,<1.5"``. ``capabilities`` is intentionally declarative: the OSS
    host compares it with its allow-list before plugin code can register a
    provider, hook, event subscription, or route. This is metadata for a
    trusted in-process plugin, not a sandbox or a security boundary.
    """

    name: str
    version: str
    required_kavach_version: str
    capabilities: tuple[str, ...] = ()
    contract_version: str = "v1"

    def __post_init__(self) -> None:
        """Reject incomplete or ambiguous metadata before the plugin runs."""
        if not self.name.strip() or not self.version.strip():
            raise ValueError("Plugin metadata requires a name and version.")
        if not self.required_kavach_version.strip():
            raise ValueError("Plugin metadata requires a Kavach version range.")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("Plugin capabilities must be unique.")
