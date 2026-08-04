from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field, model_validator


class PromptObservationRequest(BaseModel):
    """Execution evidence that identifies one observed prompt version."""

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    source_reference: str | None = None
    template: str | None = None
    content_hash: str | None = None
    variables: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_content_evidence(self) -> PromptObservationRequest:
        if self.template is None and not self.content_hash:
            raise ValueError(
                "content_hash is required when the producer does not submit prompt content."
            )
        if self.template is not None and self.content_hash is not None:
            actual = f"sha256:{hashlib.sha256(self.template.encode()).hexdigest()}"
            if self.content_hash != actual:
                raise ValueError("content_hash does not match the submitted template.")
        return self


class ModelObservationRequest(BaseModel):
    """Execution evidence that identifies one observed model version."""

    provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    source_reference: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    context_window: int = Field(gt=0)
    cost: dict[str, float] | None = None
    latency: float | None = Field(default=None, ge=0)
