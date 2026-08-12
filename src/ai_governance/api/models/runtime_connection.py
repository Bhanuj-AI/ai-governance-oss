from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ai_governance.domain.runtime_connection import RuntimeConnection


class RuntimeConnectionCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1)
    settings: dict[str, Any] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    scope: Literal["ORGANIZATION", "PROJECT"] = "ORGANIZATION"


class RuntimeConnectionUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    settings: dict[str, Any] | None = None
    secret_refs: dict[str, str] | None = None
    enabled: bool | None = None


class RuntimeConnectionResponse(BaseModel):
    runtime_connection_id: str
    display_name: str
    provider: str
    settings: dict[str, Any]
    secret_refs: dict[str, str]
    enabled: bool
    status: Literal["ACTIVE", "DISABLED"]
    organization_id: str
    project_id: str | None
    scope: Literal["ORGANIZATION", "PROJECT"]
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    last_tested_at: datetime | None
    last_test_status: str
    last_test_message: str | None
    version: int

    @classmethod
    def from_domain(cls, connection: RuntimeConnection) -> "RuntimeConnectionResponse":
        return cls(
            runtime_connection_id=connection.runtime_connection_id,
            display_name=connection.display_name,
            provider=connection.provider,
            settings=dict(connection.settings),
            secret_refs=dict(connection.secret_refs),
            enabled=connection.enabled,
            status="ACTIVE" if connection.enabled else "DISABLED",
            organization_id=connection.organization_id,
            project_id=connection.project_id,
            scope="PROJECT" if connection.project_id else "ORGANIZATION",
            created_by=connection.created_by,
            updated_by=connection.updated_by,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
            last_tested_at=connection.last_tested_at,
            last_test_status=connection.last_test_status.value,
            last_test_message=connection.last_test_message,
            version=connection.version,
        )


class RuntimeConnectionValidationResponse(BaseModel):
    valid: bool
    provider: str
    message: str


class RuntimeConnectionProviderResponse(BaseModel):
    key: str
    display_name: str
    allowed: bool


class DiscoveredRuntimeModelResponse(BaseModel):
    provider_model_id: str
