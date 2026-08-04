from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from kavach.domain.prompts import Prompt


class PromptResponse(BaseModel):
    """
    REST metadata for a prompt version.
    """

    prompt_id: str
    name: str
    version: str
    variables: list[str] = Field(
        description="Prompt input variable names.",
    )
    created_at: datetime
    created_by: str
    status: str
    provenance: str
    source_system: str | None
    source_reference: str | None
    content_hash: str | None
    content_available: bool

    @classmethod
    def from_domain(
        cls,
        prompt: Prompt,
    ) -> PromptResponse:
        return cls(
            prompt_id=prompt.prompt_id,
            name=prompt.name,
            version=prompt.version,
            variables=list(prompt.variables),
            created_at=prompt.created_at,
            created_by=prompt.created_by,
            status=prompt.status.value,
            provenance=prompt.provenance.value,
            source_system=prompt.source_system,
            source_reference=prompt.source_reference,
            content_hash=prompt.content_hash,
            content_available=prompt.content_available,
        )


class PromptDetailResponse(PromptResponse):
    """
    Full registry representation of a prompt version.

    Prompt contents are intentionally omitted from collection/discovery
    responses. A user who opens a specific governed version may inspect the
    template that the version represents.
    """

    template: str | None

    @classmethod
    def from_domain(
        cls,
        prompt: Prompt,
    ) -> PromptDetailResponse:
        return cls(
            prompt_id=prompt.prompt_id,
            name=prompt.name,
            version=prompt.version,
            variables=list(prompt.variables),
            created_at=prompt.created_at,
            created_by=prompt.created_by,
            status=prompt.status.value,
            template=prompt.template,
            provenance=prompt.provenance.value,
            source_system=prompt.source_system,
            source_reference=prompt.source_reference,
            content_hash=prompt.content_hash,
            content_available=prompt.content_available,
        )
