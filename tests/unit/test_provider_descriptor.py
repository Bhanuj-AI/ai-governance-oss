from __future__ import annotations

from ai_governance.providers.provider_capabilities import ProviderCapabilities
from ai_governance.providers.provider_descriptor import (
    ProviderDescriptor,
    normalize_provider_name,
)


def test_provider_names_normalize_to_lowercase_snake_case() -> None:
    assert normalize_provider_name("TruLens") == "trulens"
    assert normalize_provider_name("Snowflake Cortex Judge") == (
        "snowflake_cortex_judge"
    )
    assert normalize_provider_name("  Custom-Provider  ") == (
        "custom_provider"
    )


def test_provider_descriptor_removes_sensitive_metadata() -> None:
    descriptor = ProviderDescriptor(
        name="mock",
        display_name="Mock",
        version="1.0.0",
        adapter_version="1.0.0",
        capabilities=ProviderCapabilities(supported_metrics=("quality",)),
        metadata={
            "region": "us-east-1",
            "api_key": "secret",
            "token": "secret",
        },
    )

    assert descriptor.metadata == {"region": "us-east-1"}


def test_provider_descriptor_removes_nested_sensitive_metadata() -> None:
    descriptor = ProviderDescriptor(
        name="mock",
        display_name="Mock",
        version="1.0.0",
        adapter_version="1.0.0",
        capabilities=ProviderCapabilities(supported_metrics=("quality",)),
        metadata={
            "outer": {
                "safe": "value",
                "secret": "redact-me",
            },
            "items": [
                {
                    "name": "safe",
                    "password": "redact-me",
                }
            ],
        },
    )

    assert descriptor.metadata == {
        "outer": {
            "safe": "value",
        },
        "items": [
            {
                "name": "safe",
            }
        ],
    }


def test_provider_descriptor_does_not_contain_resolved_at() -> None:
    descriptor = ProviderDescriptor(
        name="mock",
        display_name="Mock",
        version="1.0.0",
        adapter_version="1.0.0",
        capabilities=ProviderCapabilities(supported_metrics=("quality",)),
    )

    assert "resolved_at" not in descriptor.to_dict()


def test_provider_descriptor_serialization_excludes_secret_reference_schema() -> None:
    descriptor = ProviderDescriptor(
        name="mock",
        display_name="Mock",
        version="1.0.0",
        adapter_version="1.0.0",
        capabilities=ProviderCapabilities(supported_metrics=("quality",)),
        configuration_schema={
            "settings": {"properties": {"region": {"type": "string"}}},
            "secret_refs": {
                "properties": {"api_key": {"type": "string"}},
            },
        },
    )

    serialized = descriptor.to_dict()

    assert "settings" in serialized["configuration_schema"]
    assert "secret_refs" not in serialized["configuration_schema"]
