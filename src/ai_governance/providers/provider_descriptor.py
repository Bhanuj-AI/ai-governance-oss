from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ai_governance.providers.provider_capabilities import ProviderCapabilities

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
)

# These are numeric execution limits or measured counters, not credentials.
# Keep the exception deliberately narrow: a key such as ``access_token`` must
# continue to be removed from any provider or provenance payload.
_SAFE_TOKEN_MEASUREMENT_KEYS = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "max_tokens",
        "max_output_tokens",
        "token_limit",
        "original_prompt_tokens",
        "token_count_kind",
    }
)


def normalize_provider_name(
    provider_name: str,
) -> str:
    """
    Convert a provider display/name value into a stable registry key.

    The normalized name is lowercase snake case so callers can use friendly
    names at API boundaries while the registry stores one canonical key.

    Example:
        normalize_provider_name("Snowflake Cortex Judge") ==
        "snowflake_cortex_judge"
    """
    normalized = provider_name.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_")


def scrub_sensitive_metadata(
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Remove secret-bearing values from descriptor metadata.

    Provider descriptors may be persisted, logged, or returned from discovery
    APIs. This helper recursively removes entries whose keys look like
    credentials so descriptors remain safe to expose.

    Example:
        scrub_sensitive_metadata({
            "region": "us-east-1",
            "api_key": "secret",
        }) == {"region": "us-east-1"}
    """
    return {
        key: _scrub_sensitive_value(value)
        for key, value in metadata.items()
        if not _is_sensitive_key(key)
    }


@dataclass(frozen=True)
class ProviderDescriptor:
    """
    Secret-free identity and capability document for an evaluation provider.

    A descriptor is what AI Governance Control Plane uses for provider discovery, registry lookup,
    and reproducibility metadata. It should contain stable adapter facts such
    as provider name, provider version, adapter version, supported metrics, and
    non-sensitive operational metadata.

    Example:
        descriptor = ProviderDescriptor(
            name="Example Judge",
            display_name="Example Judge",
            version="2026.1",
            adapter_version="1",
            capabilities=ProviderCapabilities(
                supported_metrics=("answer_relevance",),
            ),
            metadata={"region": "us-east-1"},
        )

        descriptor.name  # "example_judge"
    """

    name: str
    display_name: str
    version: str
    adapter_version: str
    capabilities: ProviderCapabilities
    config_schema_version: str = "1"
    configuration_schema: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Canonicalize provider identity and remove sensitive metadata values.
        """
        object.__setattr__(self, "name", normalize_provider_name(self.name))
        object.__setattr__(
            self,
            "metadata",
            scrub_sensitive_metadata(self.metadata),
        )
        object.__setattr__(
            self,
            "configuration_schema",
            dict(self.configuration_schema),
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Return a JSON-serializable descriptor for APIs and snapshots.
        """
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "adapter_version": self.adapter_version,
            "capabilities": self.capabilities.to_dict(),
            "config_schema_version": self.config_schema_version,
            "configuration_schema": scrub_sensitive_metadata(
                self.configuration_schema
            ),
            "metadata": dict(self.metadata),
        }


def _is_sensitive_key(
    key: str,
) -> bool:
    normalized = key.lower()
    if normalized in _SAFE_TOKEN_MEASUREMENT_KEYS:
        return False
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _scrub_sensitive_value(
    value: Any,
) -> Any:
    if isinstance(value, Mapping):
        return scrub_sensitive_metadata(value)

    if isinstance(value, list | tuple):
        return [
            _scrub_sensitive_value(item)
            for item in value
        ]

    return value
