from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from kavach.domain.assets import AssetProvenance


class PromptStatus(str, Enum):
    """
    Governance lifecycle state for a registered prompt version.
    """

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class Prompt:
    """
    Versioned prompt identity recorded by the prompt catalog.

    Prompt instances are immutable governance records. Lifecycle operations
    such as activate or archive create updated records through the registry
    service instead of mutating this object directly.
    """

    prompt_id: str
    name: str
    version: str
    template: str | None
    variables: tuple[str, ...]
    created_at: datetime
    created_by: str
    status: PromptStatus
    provenance: AssetProvenance = AssetProvenance.MANAGED
    source_system: str | None = None
    source_reference: str | None = None
    content_hash: str | None = None
    content_available: bool = True
    tenant_id: str = "org_default"
    organization_id: str = "org_default"
    project_id: str = "project_default"

    def __post_init__(self) -> None:
        self._require_non_empty("prompt_id", self.prompt_id)
        self._require_non_empty("name", self.name)
        self._require_non_empty("version", self.version)
        self._require_non_empty("created_by", self.created_by)
        self._require_non_empty("tenant_id", self.tenant_id)
        self._require_non_empty("organization_id", self.organization_id)
        self._require_non_empty("project_id", self.project_id)

        if self.content_available and self.template is None:
            raise ValueError("Prompt template is required when content is available.")
        if self.template is not None and not self.template.strip():
            raise ValueError("Prompt template must not be empty when supplied.")
        if not self.content_available and self.template is not None:
            raise ValueError("Prompt template cannot be supplied when content is unavailable.")
        if self.provenance != AssetProvenance.MANAGED:
            self._require_non_empty("source_system", self.source_system or "")
        if self.content_hash is not None:
            self._require_non_empty("content_hash", self.content_hash)

        object.__setattr__(
            self,
            "variables",
            tuple(self.variables),
        )

        if len(set(self.variables)) != len(self.variables):
            raise ValueError("Prompt variables must be unique.")

    @staticmethod
    def _require_non_empty(
        field_name: str,
        value: str,
    ) -> None:
        if not value.strip():
            raise ValueError(f"Prompt {field_name} must not be empty.")


@dataclass(frozen=True)
class PromptDiff:
    """
    Governance diff between two prompt versions.

    The unified template diff is line-oriented so reviewers can inspect prompt
    wording changes without knowing where prompts are stored.
    """

    baseline_prompt_id: str
    candidate_prompt_id: str
    template_changed: bool
    variables_added: tuple[str, ...]
    variables_removed: tuple[str, ...]
    unified_template_diff: tuple[str, ...]
