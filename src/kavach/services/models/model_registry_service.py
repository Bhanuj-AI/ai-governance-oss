from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from kavach.domain.assets import AssetProvenance
from kavach.events import EventPublisher, ResourceLifecycleEvent
from kavach.domain.models import (
    Model,
    ModelDiff,
    ModelParameterChange,
    ModelStatus,
)
from kavach.ontology.synchronization import (
    OntologySyncEventPublisherProtocol,
)
from kavach.repositories.model_repository import ModelRepository


class ModelNotFoundError(Exception):
    """
    Raised when a model registry operation references an unknown model.
    """


class ModelVersionConflictError(Exception):
    """
    Raised when a provider, model name, and version already exist.
    """


class ModelLifecycleError(Exception):
    """
    Raised when a model lifecycle transition is not allowed.
    """


class ModelRegistryService:
    """
    Application service for governed model lifecycle management.

    The service owns enterprise model governance rules while repositories remain
    persistence-only.
    """

    def __init__(
        self,
        model_repository: ModelRepository,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol
        | None = None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self._model_repository = model_repository
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ontology_event_publisher = ontology_event_publisher
        self._event_publisher = event_publisher

    def register_model(
        self,
        provider: str,
        model_name: str,
        version: str,
        parameters: dict[str, Any],
        context_window: int,
        creator: str,
        cost: dict[str, float] | None = None,
        latency: float | None = None,
    ) -> Model:
        """
        Register a new model version in DRAFT status.
        """

        self._ensure_version_available(
            provider=provider,
            model_name=model_name,
            version=version,
        )

        model = Model(
            model_id=self._id_generator(),
            provider=provider,
            model_name=model_name,
            version=version,
            parameters=parameters,
            cost=cost,
            latency=latency,
            context_window=context_window,
            creator=creator,
            created_at=self._clock(),
            status=ModelStatus.DRAFT,
        )

        self._model_repository.save(model)
        self._publish_model_event("ModelVersionRegistered", model)

        return model

    def create_model_version(
        self,
        model_id: str,
        version: str,
        creator: str,
        parameters: dict[str, Any] | None = None,
        cost: dict[str, float] | None = None,
        latency: float | None = None,
        context_window: int | None = None,
    ) -> Model:
        """
        Create a new DRAFT version from an existing model.
        """

        source = self._get_model(model_id)
        self._ensure_version_available(
            provider=source.provider,
            model_name=source.model_name,
            version=version,
        )

        model = Model(
            model_id=self._id_generator(),
            provider=source.provider,
            model_name=source.model_name,
            version=version,
            parameters=(
                parameters
                if parameters is not None
                else source.parameters
            ),
            cost=cost if cost is not None else source.cost,
            latency=latency if latency is not None else source.latency,
            context_window=(
                context_window
                if context_window is not None
                else source.context_window
            ),
            creator=creator,
            created_at=self._clock(),
            status=ModelStatus.DRAFT,
        )

        self._model_repository.save(model)
        self._publish_model_event("ModelVersionRegistered", model)

        return model

    def observe_model(
        self,
        *,
        provider: str,
        model_name: str,
        version: str,
        source_system: str,
        source_reference: str | None,
        parameters: dict[str, Any],
        context_window: int,
        observed_by: str,
        cost: dict[str, float] | None = None,
        latency: float | None = None,
    ) -> Model:
        """Record an exact runtime model configuration as execution evidence."""

        existing = self._model_repository.find_by_provider_name_and_version(
            provider, model_name, version
        )
        if existing is not None:
            if (
                existing.provenance == AssetProvenance.OBSERVED
                and existing.source_system == source_system
                and existing.source_reference == source_reference
                and existing.parameters == parameters
                and existing.context_window == context_window
                and existing.cost == cost
                and existing.latency == latency
            ):
                return existing
            raise ModelVersionConflictError(
                f"Model '{provider}/{model_name}' version '{version}' is already recorded with different evidence."
            )

        identity = "|".join(
            (source_system, source_reference or "", provider, model_name, version)
        )
        model = Model(
            model_id=str(uuid5(NAMESPACE_URL, f"kavach:observed-model:{identity}")),
            provider=provider,
            model_name=model_name,
            version=version,
            parameters=parameters,
            cost=cost,
            latency=latency,
            context_window=context_window,
            creator=observed_by,
            created_at=self._clock(),
            status=ModelStatus.ACTIVE,
            provenance=AssetProvenance.OBSERVED,
            source_system=source_system,
            source_reference=source_reference,
        )
        self._model_repository.save(model)
        self._publish_model_event("ModelVersionObserved", model)
        return model

    def activate_model_version(
        self,
        model_id: str,
    ) -> Model:
        """
        Activate one model version and deprecate the previous active version.
        """

        model = self._get_model(model_id)

        if model.status == ModelStatus.ARCHIVED:
            raise ModelLifecycleError(
                "Archived models cannot be activated."
            )

        for existing in self.list_versions(
            provider=model.provider,
            model_name=model.model_name,
        ):
            if (
                existing.model_id != model.model_id
                and existing.status == ModelStatus.ACTIVE
            ):
                deprecated = replace(existing, status=ModelStatus.DEPRECATED)
                self._model_repository.save(deprecated)
                self._publish_model_event(
                    "ModelVersionDeprecated",
                    deprecated,
                )

        activated = replace(model, status=ModelStatus.ACTIVE)
        self._model_repository.save(activated)
        self._publish_model_event("ModelVersionActivated", activated)

        return activated

    def deprecate_model_version(
        self,
        model_id: str,
    ) -> Model:
        """
        Mark a model version as deprecated while preserving history.
        """

        model = self._get_model(model_id)

        if model.status == ModelStatus.ARCHIVED:
            raise ModelLifecycleError(
                "Archived models cannot be deprecated."
            )

        deprecated = replace(model, status=ModelStatus.DEPRECATED)
        self._model_repository.save(deprecated)
        self._publish_model_event("ModelVersionDeprecated", deprecated)

        return deprecated

    def archive_model(
        self,
        model_id: str,
    ) -> Model:
        """
        Archive a model version so it is no longer deployable.
        """

        model = self._get_model(model_id)

        if model.status == ModelStatus.ARCHIVED:
            return model

        archived = replace(model, status=ModelStatus.ARCHIVED)
        self._model_repository.save(archived)
        self._publish_model_event("ModelVersionArchived", archived)

        return archived

    def get_model(
        self,
        model_id: str,
    ) -> Model:
        """
        Retrieve a model by registry ID.
        """

        return self._get_model(model_id)

    def get_model_version(
        self,
        provider: str,
        model_name: str,
        version: str,
    ) -> Model:
        """
        Retrieve a specific logical model version.
        """

        model = self._model_repository.find_by_provider_name_and_version(
            provider=provider,
            model_name=model_name,
            version=version,
        )

        if model is None:
            raise ModelNotFoundError(
                f"Model '{provider}/{model_name}' version '{version}' does not exist."
            )

        return model

    def list_models(self) -> list[Model]:
        """
        Return every model version in the registry.
        """

        return self._model_repository.find_all()

    def list_versions(
        self,
        provider: str,
        model_name: str,
    ) -> list[Model]:
        """
        Return every version for one logical model.
        """

        return self._model_repository.find_by_logical_model(
            provider=provider,
            model_name=model_name,
        )

    def compare_model_versions(
        self,
        baseline_model_id: str,
        candidate_model_id: str,
    ) -> ModelDiff:
        """
        Compare two model versions by governed metadata.
        """

        baseline = self._get_model(baseline_model_id)
        candidate = self._get_model(candidate_model_id)
        baseline_parameters = set(baseline.parameters.keys())
        candidate_parameters = set(candidate.parameters.keys())

        return ModelDiff(
            baseline_model_id=baseline.model_id,
            candidate_model_id=candidate.model_id,
            provider_changed=baseline.provider != candidate.provider,
            version_changed=baseline.version != candidate.version,
            context_window_changed=(
                baseline.context_window != candidate.context_window
            ),
            cost_changed=baseline.cost != candidate.cost,
            latency_changed=baseline.latency != candidate.latency,
            parameters_added=tuple(
                sorted(candidate_parameters - baseline_parameters)
            ),
            parameters_removed=tuple(
                sorted(baseline_parameters - candidate_parameters)
            ),
            parameters_changed=tuple(
                ModelParameterChange(
                    parameter_name=parameter_name,
                    baseline_value=baseline.parameters[parameter_name],
                    candidate_value=candidate.parameters[parameter_name],
                )
                for parameter_name in sorted(
                    baseline_parameters & candidate_parameters
                )
                if baseline.parameters[parameter_name]
                != candidate.parameters[parameter_name]
            ),
        )

    def _get_model(
        self,
        model_id: str,
    ) -> Model:
        model = self._model_repository.find_by_id(model_id)

        if model is None:
            raise ModelNotFoundError(
                f"Model '{model_id}' does not exist."
            )

        return model

    def _ensure_version_available(
        self,
        provider: str,
        model_name: str,
        version: str,
    ) -> None:
        if (
            self._model_repository.find_by_provider_name_and_version(
                provider=provider,
                model_name=model_name,
                version=version,
            )
            is not None
        ):
            raise ModelVersionConflictError(
                f"Model '{provider}/{model_name}' version '{version}' already exists."
            )

    def _publish_model_event(
        self,
        event_type: str,
        model: Model,
    ) -> None:
        if self._ontology_event_publisher is not None:
            self._ontology_event_publisher.publish_entity_event(
                event_type,
                entity_type="ModelVersion",
                entity_id=model.model_id,
                scope_identifier="model_registry",
                payload={
                    "model_id": model.model_id,
                    "provider": model.provider,
                    "model_name": model.model_name,
                    "version": model.version,
                    "status": model.status.value,
                    "provenance": model.provenance.value,
                    "source_system": model.source_system,
                },
            )
        if self._event_publisher is None:
            return
        state = {
            "ModelVersionRegistered": "registered",
            "ModelVersionObserved": "version.created",
            "ModelVersionArchived": "archived",
        }.get(event_type)
        if state is not None:
            import asyncio

            asyncio.run(
                self._event_publisher.publish(
                    ResourceLifecycleEvent(
                        tenant={
                            "tenant_id": model.tenant_id,
                            "organization_id": model.organization_id,
                            "project_id": model.project_id,
                        },
                        resource_kind="asset",
                        resource_id=model.model_id,
                        state=state,
                        payload={
                            "asset_type": "ModelVersion",
                            "version": model.version,
                            "status": model.status.value,
                        },
                    )
                )
            )
