from datetime import UTC, datetime

import pytest

from kavach.domain.models import ModelStatus
from kavach.domain.assets import AssetProvenance
from kavach.repositories.in_memory_model_repository import (
    InMemoryModelRepository,
)
from kavach.services.models import (
    ModelLifecycleError,
    ModelRegistryService,
    ModelVersionConflictError,
)


def test_model_registry_registers_model() -> None:
    service = _create_service()

    model = service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={
            "temperature": 0.0,
        },
        cost={
            "input_per_1k": 0.01,
        },
        latency=0.42,
        context_window=128000,
        creator="governance-admin",
    )

    assert model.model_id == "model-1"
    assert model.provider == "OpenAI"
    assert model.model_name == "GPT-4.1"
    assert model.version == "2026-06-25"
    assert model.parameters == {"temperature": 0.0}
    assert model.cost == {"input_per_1k": 0.01}
    assert model.latency == 0.42
    assert model.context_window == 128000
    assert model.creator == "governance-admin"
    assert model.created_at == datetime(2026, 6, 25, tzinfo=UTC)
    assert model.status == ModelStatus.DRAFT


def test_model_registry_rejects_duplicate_model_version() -> None:
    service = _create_service()
    service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={},
        context_window=128000,
        creator="governance-admin",
    )

    with pytest.raises(ModelVersionConflictError):
        service.register_model(
            provider="OpenAI",
            model_name="GPT-4.1",
            version="2026-06-25",
            parameters={},
            context_window=128000,
            creator="governance-admin",
        )


def test_model_registry_creates_new_version() -> None:
    service = _create_service()
    original = service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={"temperature": 0.0},
        context_window=128000,
        creator="governance-admin",
    )

    versioned = service.create_model_version(
        model_id=original.model_id,
        version="2026-07-01",
        parameters={"temperature": 0.2, "reasoning": "medium"},
        context_window=256000,
        creator="model-owner",
    )

    assert versioned.model_id == "model-2"
    assert versioned.provider == original.provider
    assert versioned.model_name == original.model_name
    assert versioned.version == "2026-07-01"
    assert versioned.parameters == {
        "temperature": 0.2,
        "reasoning": "medium",
    }
    assert versioned.context_window == 256000
    assert versioned.status == ModelStatus.DRAFT


def test_model_registry_activates_model_and_deprecates_previous_active() -> None:
    service = _create_service()
    original = service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={},
        context_window=128000,
        creator="governance-admin",
    )
    candidate = service.create_model_version(
        model_id=original.model_id,
        version="2026-07-01",
        creator="model-owner",
    )

    activated_original = service.activate_model_version(original.model_id)
    activated_candidate = service.activate_model_version(candidate.model_id)

    assert activated_original.status == ModelStatus.ACTIVE
    assert activated_candidate.status == ModelStatus.ACTIVE
    assert service.get_model(original.model_id).status == ModelStatus.DEPRECATED
    assert service.get_model(candidate.model_id).status == ModelStatus.ACTIVE


def test_model_registry_deprecates_model_version() -> None:
    service = _create_service()
    model = service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={},
        context_window=128000,
        creator="governance-admin",
    )

    deprecated = service.deprecate_model_version(model.model_id)

    assert deprecated.status == ModelStatus.DEPRECATED


def test_model_registry_archives_model() -> None:
    service = _create_service()
    model = service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={},
        context_window=128000,
        creator="governance-admin",
    )

    archived = service.archive_model(model.model_id)

    assert archived.status == ModelStatus.ARCHIVED
    assert service.get_model(model.model_id).status == ModelStatus.ARCHIVED


def test_model_registry_rejects_activation_of_archived_model() -> None:
    service = _create_service()
    model = service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={},
        context_window=128000,
        creator="governance-admin",
    )
    service.archive_model(model.model_id)

    with pytest.raises(ModelLifecycleError):
        service.activate_model_version(model.model_id)


def test_model_registry_retrieves_specific_version_and_lists_versions() -> None:
    service = _create_service()
    original = service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={},
        context_window=128000,
        creator="governance-admin",
    )
    versioned = service.create_model_version(
        model_id=original.model_id,
        version="2026-07-01",
        creator="model-owner",
    )

    found = service.get_model_version(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-07-01",
    )
    versions = service.list_versions(
        provider="OpenAI",
        model_name="GPT-4.1",
    )

    assert found == versioned
    assert versions == [
        original,
        versioned,
    ]
    assert service.list_models() == [
        original,
        versioned,
    ]


def test_model_registry_observes_runtime_configuration_idempotently() -> None:
    service = _create_service()

    observed = service.observe_model(
        provider="OpenAI",
        model_name="gpt-5",
        version="2026-06",
        source_system="evaluation-sdk",
        source_reference="run-123",
        parameters={"temperature": 0.2, "max_tokens": 800},
        context_window=128000,
        observed_by="runtime-agent",
    )
    repeated = service.observe_model(
        provider="OpenAI",
        model_name="gpt-5",
        version="2026-06",
        source_system="evaluation-sdk",
        source_reference="run-123",
        parameters={"temperature": 0.2, "max_tokens": 800},
        context_window=128000,
        observed_by="runtime-agent",
    )

    assert observed.provenance == AssetProvenance.OBSERVED
    assert observed.source_system == "evaluation-sdk"
    assert observed.status == ModelStatus.ACTIVE
    assert repeated == observed


def test_model_registry_rejects_conflicting_observed_evidence() -> None:
    service = _create_service()
    service.observe_model(
        provider="OpenAI",
        model_name="gpt-5",
        version="2026-06",
        source_system="evaluation-sdk",
        source_reference="run-123",
        parameters={"temperature": 0.2},
        context_window=128000,
        observed_by="runtime-agent",
    )

    with pytest.raises(ModelVersionConflictError):
        service.observe_model(
            provider="OpenAI",
            model_name="gpt-5",
            version="2026-06",
            source_system="evaluation-sdk",
            source_reference="run-123",
            parameters={"temperature": 0.3},
            context_window=128000,
            observed_by="runtime-agent",
        )


def test_model_registry_compares_model_versions() -> None:
    service = _create_service()
    original = service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={"temperature": 0.0, "reasoning": "low"},
        cost={"input_per_1k": 0.01},
        latency=0.42,
        context_window=128000,
        creator="governance-admin",
    )
    candidate = service.create_model_version(
        model_id=original.model_id,
        version="2026-07-01",
        parameters={"temperature": 0.2, "tool_choice": "auto"},
        cost={"input_per_1k": 0.02},
        latency=0.5,
        context_window=256000,
        creator="model-owner",
    )

    diff = service.compare_model_versions(
        baseline_model_id=original.model_id,
        candidate_model_id=candidate.model_id,
    )

    assert diff.baseline_model_id == original.model_id
    assert diff.candidate_model_id == candidate.model_id
    assert diff.provider_changed is False
    assert diff.version_changed is True
    assert diff.context_window_changed is True
    assert diff.cost_changed is True
    assert diff.latency_changed is True
    assert diff.parameters_added == ("tool_choice",)
    assert diff.parameters_removed == ("reasoning",)
    assert diff.parameters_changed[0].parameter_name == "temperature"
    assert diff.parameters_changed[0].baseline_value == 0.0
    assert diff.parameters_changed[0].candidate_value == 0.2
    assert diff.has_changes is True


def _create_service() -> ModelRegistryService:
    ids = iter(["model-1", "model-2", "model-3"])

    return ModelRegistryService(
        model_repository=InMemoryModelRepository(),
        id_generator=lambda: next(ids),
        clock=lambda: datetime(2026, 6, 25, tzinfo=UTC),
    )
