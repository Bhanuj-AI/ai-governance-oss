from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from kavach.providers.provider_descriptor import ProviderDescriptor


@dataclass(frozen=True)
class ProviderDescriptorSnapshot:
    """
    Immutable provider descriptor copy attached to an evaluation result.

    Snapshots capture which provider contract was resolved when an evaluation
    ran. They make stored evaluations reproducible even if a provider is later
    upgraded, reconfigured, or replaced in the registry.

    The descriptor hash is calculated from the descriptor content only. The
    resolution timestamp is stored separately so the hash can be used to group
    evaluations that ran against the same provider contract.

    Example:
        snapshot = ProviderDescriptorSnapshot.from_descriptor(descriptor)
        result.provider_descriptor_snapshot = snapshot.to_dict()

        restored = ProviderDescriptorSnapshot.from_dict(snapshot.to_dict())
    """

    provider_name: str
    provider_version: str
    adapter_version: str
    capabilities: Mapping[str, Any]
    config_schema_version: str
    metadata: Mapping[str, Any]
    resolved_at: datetime
    descriptor_hash: str | None

    @classmethod
    def from_descriptor(
        cls,
        descriptor: ProviderDescriptor,
    ) -> ProviderDescriptorSnapshot:
        """
        Create a timestamped snapshot from a live provider descriptor.
        """
        resolved_at = datetime.now(UTC)
        return cls(
            provider_name=descriptor.name,
            provider_version=descriptor.version,
            adapter_version=descriptor.adapter_version,
            capabilities=descriptor.capabilities.to_dict(),
            config_schema_version=descriptor.config_schema_version,
            metadata=dict(descriptor.metadata),
            resolved_at=resolved_at,
            descriptor_hash=_descriptor_hash(descriptor),
        )

    @classmethod
    def from_dict(
        cls,
        values: Mapping[str, Any],
    ) -> ProviderDescriptorSnapshot:
        """
        Rehydrate a snapshot from persisted JSON-compatible values.
        """
        resolved_at = values["resolved_at"]
        return cls(
            provider_name=values["provider_name"],
            provider_version=values["provider_version"],
            adapter_version=values["adapter_version"],
            capabilities=dict(values["capabilities"]),
            config_schema_version=values["config_schema_version"],
            metadata=dict(values.get("metadata", {})),
            resolved_at=datetime.fromisoformat(resolved_at)
            if isinstance(resolved_at, str)
            else resolved_at,
            descriptor_hash=values.get("descriptor_hash"),
        )

    def __post_init__(self) -> None:
        """
        Defensive-copy mappings so snapshot instances are stable.
        """
        object.__setattr__(self, "capabilities", dict(self.capabilities))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """
        Return a JSON-serializable snapshot for persistence or APIs.
        """
        return {
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "adapter_version": self.adapter_version,
            "capabilities": dict(self.capabilities),
            "config_schema_version": self.config_schema_version,
            "metadata": dict(self.metadata),
            "resolved_at": self.resolved_at.isoformat(),
            "descriptor_hash": self.descriptor_hash,
        }


def _descriptor_hash(
    descriptor: ProviderDescriptor,
) -> str:
    """
    Build a deterministic content hash for a provider descriptor.
    """
    encoded = json.dumps(
        descriptor.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
