from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ai_governance.domain.models import Model


class ModelResponse(BaseModel):
    """
    REST metadata for a registered model version.
    """

    model_id: str
    provider: str
    model_name: str
    version: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, float] | None
    latency: float | None
    context_window: int
    creator: str
    created_at: datetime
    status: str
    provenance: str
    source_system: str | None
    source_reference: str | None

    @classmethod
    def from_domain(
        cls,
        model: Model,
    ) -> ModelResponse:
        return cls(
            model_id=model.model_id,
            provider=model.provider,
            model_name=model.model_name,
            version=model.version,
            parameters=dict(model.parameters),
            cost=dict(model.cost) if model.cost is not None else None,
            latency=model.latency,
            context_window=model.context_window,
            creator=model.creator,
            created_at=model.created_at,
            status=model.status.value,
            provenance=model.provenance.value,
            source_system=model.source_system,
            source_reference=model.source_reference,
        )


class ModelRegisterRequest(BaseModel):
    """Register a managed model/runtime configuration without credentials."""

    provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, float] | None = None
    latency: float | None = Field(default=None, ge=0)
    context_window: int = Field(gt=0)


class ModelVersionCreateRequest(BaseModel):
    """Create an immutable managed version from an existing managed model."""

    version: str = Field(min_length=1)
    parameters: dict[str, Any] | None = None
    cost: dict[str, float] | None = None
    latency: float | None = Field(default=None, ge=0)
    context_window: int | None = Field(default=None, gt=0)


class RuntimeModelProviderResponse(BaseModel):
    """One configured runtime-provider choice for managed registration."""

    key: str
    display_name: str
    allowed: bool
