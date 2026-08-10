from __future__ import annotations

from abc import ABC, abstractmethod

from ai_governance.domain.prompts import Prompt


class PromptRepository(ABC):
    """
    Persistence contract for versioned prompt artifacts.

    Repository implementations store prompt records only. Lifecycle decisions
    such as activation, archival, and version conflict checks belong in the
    prompt registry service.
    """

    @abstractmethod
    def save(
        self,
        prompt: Prompt,
    ) -> None:
        pass

    @abstractmethod
    def find_by_id(
        self,
        prompt_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Prompt | None:
        pass

    @abstractmethod
    def find_by_name(
        self,
        name: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[Prompt]:
        pass

    @abstractmethod
    def find_by_name_and_version(
        self,
        name: str,
        version: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Prompt | None:
        pass

    @abstractmethod
    def find_all(
        self, organization_id: str = "org_default", project_id: str = "project_default"
    ) -> list[Prompt]:
        pass
