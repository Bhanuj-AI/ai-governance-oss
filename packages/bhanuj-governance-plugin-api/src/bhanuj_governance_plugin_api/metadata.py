"""Versioned identity and compatibility declarations for runtime plugins."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

SPI_VERSION = "1"
"""The supported major version of the independently released Plugin API."""

LEGACY_CONTRACT_VERSION = "v1"
"""Compatibility spelling retained for diagnostics emitted by existing hosts."""

CANONICAL_PLUGIN_ENTRY_POINT_GROUP = "bhanuj.governance.plugins"
"""The Python packaging entry-point group for new BHANUJ plugins."""

LEGACY_PLUGIN_ENTRY_POINT_GROUP = "ai_governance.plugins"
"""Temporarily supported entry-point group for pre-Plugin-API extensions."""


class PluginStatus(StrEnum):
    """Lifecycle state reported by a BHANUJ plugin host."""

    DISCOVERED = "discovered"
    REGISTERED = "registered"
    ACTIVE = "active"
    DISABLED = "disabled"
    FAILED = "failed"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class PluginMetadata:
    """Immutable identity, host compatibility, and Plugin API compatibility."""

    name: str
    version: str
    required_ai_governance_version: str
    capabilities: tuple[str, ...] = ()
    spi_version: str = SPI_VERSION
    contract_version: str = LEGACY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ValueError("Plugin metadata requires a name and version.")
        if not self.required_ai_governance_version.strip():
            raise ValueError(
                "Plugin metadata requires an AI Governance Control Plane version range."
            )
        if not self.spi_version.isdigit() or int(self.spi_version) < 1:
            raise ValueError("Plugin metadata spi_version must be a positive major.")
        if self.contract_version != f"v{self.spi_version}":
            raise ValueError(
                "Plugin metadata contract_version must match its SPI major version."
            )
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("Plugin capabilities must be unique.")
