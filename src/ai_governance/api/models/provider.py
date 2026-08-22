from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ai_governance.providers.provider_capabilities import ProviderCapabilities
from ai_governance.providers.provider_descriptor import ProviderDescriptor


class ProviderCapabilityResponse(BaseModel):
    """
    REST representation of provider capabilities.
    """

    supported_metrics: list[str] = Field(
        description="Canonical metrics supported by the provider adapter.",
    )
    supported_evaluation_modes: list[str] = Field(
        description="Evaluation execution modes supported by the adapter.",
    )
    supports_batch: bool
    supports_async: bool
    supports_artifacts: bool
    supports_explanations: bool
    supports_row_level_results: bool
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive provider capability metadata.",
    )

    @classmethod
    def from_domain(
        cls,
        capabilities: ProviderCapabilities,
    ) -> ProviderCapabilityResponse:
        return cls(
            supported_metrics=list(capabilities.supported_metrics),
            supported_evaluation_modes=list(capabilities.supported_evaluation_modes),
            supports_batch=capabilities.supports_batch,
            supports_async=capabilities.supports_async,
            supports_artifacts=capabilities.supports_artifacts,
            supports_explanations=capabilities.supports_explanations,
            supports_row_level_results=(capabilities.supports_row_level_results),
            metadata=dict(capabilities.metadata),
        )


class ProviderResponse(BaseModel):
    """
    REST representation of a provider descriptor.
    """

    name: str
    display_name: str
    version: str
    adapter_version: str
    capabilities: ProviderCapabilityResponse
    config_schema_version: str
    configuration_schema: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(
        cls,
        descriptor: ProviderDescriptor,
    ) -> ProviderResponse:
        return cls(
            name=descriptor.name,
            display_name=descriptor.display_name,
            version=descriptor.version,
            adapter_version=descriptor.adapter_version,
            capabilities=ProviderCapabilityResponse.from_domain(
                descriptor.capabilities
            ),
            config_schema_version=descriptor.config_schema_version,
            configuration_schema=dict(descriptor.configuration_schema),
            metadata=dict(descriptor.metadata),
        )


class ProviderInstallationCreateRequest(BaseModel):
    provider_type: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=120)
    settings: dict[str, Any] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    scope: Literal["ORGANIZATION", "PROJECT"] = "ORGANIZATION"


class ProviderInstallationUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    settings: dict[str, Any] | None = None
    secret_refs: dict[str, str] | None = None
    enabled: bool | None = None


class ProviderInstallationResponse(BaseModel):
    installation_id: str
    provider_type: str
    adapter_version: str
    display_name: str
    settings: dict[str, Any]
    secret_refs: dict[str, str]
    enabled: bool
    organization_id: str
    project_id: str | None
    scope: Literal["ORGANIZATION", "PROJECT"]
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    version: int

    @classmethod
    def from_domain(cls, item) -> ProviderInstallationResponse:
        return cls(
            installation_id=item.installation_id,
            provider_type=item.provider_type,
            adapter_version=item.adapter_version,
            display_name=item.display_name,
            settings=dict(item.settings),
            secret_refs=dict(item.secret_refs),
            enabled=item.enabled,
            organization_id=item.organization_id,
            project_id=item.project_id,
            scope="PROJECT" if item.project_id else "ORGANIZATION",
            created_by=item.created_by,
            updated_by=item.updated_by,
            created_at=item.created_at,
            updated_at=item.updated_at,
            version=item.version,
        )


class ProviderInstallationValidationResponse(BaseModel):
    valid: bool
    provider_type: str
    message: str
