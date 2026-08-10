from __future__ import annotations

from abc import ABC, abstractmethod

from ai_governance.decisions import DecisionTargetType, PolicyStatus
from ai_governance.decisions.policy_administration import (
    PolicyDefinition,
    PolicyVersion,
)
from ai_governance.decisions.policy_enums import PolicyCategory


class PolicyAdministrationConflictError(Exception):
    """
    Raised when stored policy state would violate admin invariants.
    """


class PolicyAdministrationRepository(ABC):
    """
    Persistence contract for Studio policy administration.
    """

    @abstractmethod
    def save_definition(
        self,
        definition: PolicyDefinition,
    ) -> None:
        pass

    @abstractmethod
    def get_definition(
        self,
        policy_id: str,
    ) -> PolicyDefinition | None:
        pass

    @abstractmethod
    def list_definitions(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        search: str | None = None,
        owner: str | None = None,
        category: PolicyCategory | str | None = None,
        status: PolicyStatus | str | None = None,
        target_type: DecisionTargetType | str | None = None,
        effect: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PolicyDefinition]:
        pass

    @abstractmethod
    def save_version(
        self,
        version: PolicyVersion,
    ) -> None:
        pass

    @abstractmethod
    def get_version(
        self,
        policy_id: str,
        version: str,
    ) -> PolicyVersion | None:
        pass

    @abstractmethod
    def list_versions(
        self,
        policy_id: str,
    ) -> list[PolicyVersion]:
        pass

    @abstractmethod
    def get_active_version(
        self,
        policy_id: str,
    ) -> PolicyVersion | None:
        pass
