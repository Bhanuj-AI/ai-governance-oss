from __future__ import annotations

from abc import ABC, abstractmethod

from kavach.domain.models import Model


class ModelRepository(ABC):
    """
    Persistence contract for governed model versions.

    Repositories store immutable model records. Lifecycle and governance rules
    are owned by ModelRegistryService.
    """

    @abstractmethod
    def save(
        self,
        model: Model,
    ) -> None:
        pass

    @abstractmethod
    def find_by_id(
        self,
        model_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Model | None:
        pass

    @abstractmethod
    def find_by_logical_model(
        self,
        provider: str,
        model_name: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[Model]:
        pass

    @abstractmethod
    def find_by_provider_name_and_version(
        self,
        provider: str,
        model_name: str,
        version: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Model | None:
        pass

    @abstractmethod
    def find_all(
        self, organization_id: str = "org_default", project_id: str = "project_default"
    ) -> list[Model]:
        pass
