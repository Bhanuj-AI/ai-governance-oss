from __future__ import annotations

from kavach.domain.models import Model
from kavach.repositories.model_repository import ModelRepository


class InMemoryModelRepository(ModelRepository):
    """
    In-memory ModelRepository used by tests and local workflows.
    """

    def __init__(self) -> None:
        self._models_by_id: dict[str, Model] = {}

    def save(
        self,
        model: Model,
    ) -> None:
        self._models_by_id[model.model_id] = model

    def find_by_id(
        self,
        model_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Model | None:
        model = self._models_by_id.get(model_id)
        return model if model and model.organization_id == organization_id and model.project_id == project_id else None

    def find_by_logical_model(
        self,
        provider: str,
        model_name: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[Model]:
        return [
            model
            for model in self._models_by_id.values()
            if model.provider == provider and model.model_name == model_name and model.organization_id == organization_id and model.project_id == project_id
        ]

    def find_by_provider_name_and_version(
        self,
        provider: str,
        model_name: str,
        version: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Model | None:
        return next(
            (
                model
                for model in self._models_by_id.values()
                if model.provider == provider
                and model.model_name == model_name
                and model.version == version
                and model.organization_id == organization_id
                and model.project_id == project_id
            ),
            None,
        )

    def find_all(self, organization_id: str = "org_default", project_id: str = "project_default") -> list[Model]:
        return [model for model in self._models_by_id.values() if model.organization_id == organization_id and model.project_id == project_id]
