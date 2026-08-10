from __future__ import annotations

from ai_governance.domain.prompts import Prompt
from ai_governance.repositories.prompt_repository import PromptRepository


class InMemoryPromptRepository(PromptRepository):
    """
    In-memory PromptRepository used by tests and local workflows.
    """

    def __init__(self) -> None:
        self._prompts_by_id: dict[str, Prompt] = {}

    def save(
        self,
        prompt: Prompt,
    ) -> None:
        self._prompts_by_id[prompt.prompt_id] = prompt

    def find_by_id(
        self,
        prompt_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Prompt | None:
        prompt = self._prompts_by_id.get(prompt_id)
        return prompt if prompt and prompt.organization_id == organization_id and prompt.project_id == project_id else None

    def find_by_name(
        self,
        name: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[Prompt]:
        return [
            prompt
            for prompt in self._prompts_by_id.values()
            if prompt.name == name and prompt.organization_id == organization_id and prompt.project_id == project_id
        ]

    def find_by_name_and_version(
        self,
        name: str,
        version: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Prompt | None:
        return next(
            (
                prompt
                for prompt in self._prompts_by_id.values()
                if prompt.name == name and prompt.version == version and prompt.organization_id == organization_id and prompt.project_id == project_id
            ),
            None,
        )

    def find_all(self, organization_id: str = "org_default", project_id: str = "project_default") -> list[Prompt]:
        return [prompt for prompt in self._prompts_by_id.values() if prompt.organization_id == organization_id and prompt.project_id == project_id]
