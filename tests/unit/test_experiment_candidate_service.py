from datetime import UTC, datetime

import pytest

from kavach.domain.experiments import ExperimentCandidate
from kavach.repositories.in_memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from kavach.repositories.in_memory_experiment_candidate_repository import (
    InMemoryExperimentCandidateRepository,
)
from kavach.repositories.in_memory_experiment_repository import (
    InMemoryExperimentRepository,
)
from kavach.repositories.in_memory_model_repository import (
    InMemoryModelRepository,
)
from kavach.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)
from kavach.services.datasets import DatasetRegistryService
from kavach.services.experiments import (
    ExperimentCandidateLifecycleError,
    ExperimentCandidateReferenceError,
    ExperimentCandidateService,
    ExperimentService,
)
from kavach.services.models import ModelRegistryService
from kavach.services.prompts import PromptRegistryService


def test_candidate_service_creates_candidate() -> None:
    services = _create_services()
    experiment = services["experiment_service"].create_experiment(
        name="support-benchmark",
        description="Compare support assistant variants.",
        owner="governance-team",
    )
    prompt, model, dataset = _create_assets(services)

    candidate = services["candidate_service"].create_candidate(
        experiment_id=experiment.experiment_id,
        name="Baseline",
        prompt_id=prompt.prompt_id,
        prompt_version=prompt.version,
        model_id=model.model_id,
        model_version=model.version,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        evaluation_provider="TruLens",
        temperature=0.0,
        top_p=1.0,
        max_tokens=4096,
        metadata={"tier": "baseline"},
    )

    assert candidate.candidate_id == "candidate-1"
    assert candidate.name == "Baseline"
    assert candidate.evaluation_provider == "TruLens"
    assert candidate.metadata == {"tier": "baseline"}


def test_candidate_service_registers_candidate() -> None:
    services = _create_services()
    experiment = services["experiment_service"].create_experiment(
        name="support-benchmark",
        description="Compare support assistant variants.",
        owner="governance-team",
    )
    prompt, model, dataset = _create_assets(services)
    candidate = ExperimentCandidate(
        candidate_id="candidate-manual",
        experiment_id=experiment.experiment_id,
        name="Manual",
        prompt_id=prompt.prompt_id,
        prompt_version=prompt.version,
        model_id=model.model_id,
        model_version=model.version,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        evaluation_provider="TruLens",
        temperature=0.1,
        top_p=0.9,
        max_tokens=2048,
        metadata={"source": "manual"},
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
    )

    stored = services["candidate_service"].register_candidate(candidate)

    assert stored == candidate
    assert (
        services["candidate_service"].get_candidate("candidate-manual")
        == candidate
    )


def test_candidate_service_rejects_candidate_for_running_experiment() -> None:
    services = _create_services()
    experiment = services["experiment_service"].create_experiment(
        name="support-benchmark",
        description="Compare support assistant variants.",
        owner="governance-team",
    )
    prompt, model, dataset = _create_assets(services)
    services["experiment_service"].start_experiment(experiment.experiment_id)

    with pytest.raises(ExperimentCandidateLifecycleError):
        services["candidate_service"].create_candidate(
            experiment_id=experiment.experiment_id,
            name="Baseline",
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            model_id=model.model_id,
            model_version=model.version,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            evaluation_provider="TruLens",
            temperature=0.0,
            top_p=1.0,
            max_tokens=4096,
        )


def test_candidate_service_rejects_archived_prompt_reference() -> None:
    services = _create_services()
    experiment = services["experiment_service"].create_experiment(
        name="support-benchmark",
        description="Compare support assistant variants.",
        owner="governance-team",
    )
    prompt, model, dataset = _create_assets(services)
    services["prompt_service"].archive_prompt(prompt.prompt_id)

    with pytest.raises(ExperimentCandidateReferenceError):
        services["candidate_service"].create_candidate(
            experiment_id=experiment.experiment_id,
            name="Archived Prompt",
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            model_id=model.model_id,
            model_version=model.version,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            evaluation_provider="TruLens",
            temperature=0.0,
            top_p=1.0,
            max_tokens=4096,
        )


def test_candidate_service_rejects_version_mismatch() -> None:
    services = _create_services()
    experiment = services["experiment_service"].create_experiment(
        name="support-benchmark",
        description="Compare support assistant variants.",
        owner="governance-team",
    )
    prompt, model, dataset = _create_assets(services)

    with pytest.raises(ExperimentCandidateReferenceError):
        services["candidate_service"].create_candidate(
            experiment_id=experiment.experiment_id,
            name="Wrong Version",
            prompt_id=prompt.prompt_id,
            prompt_version="v999",
            model_id=model.model_id,
            model_version=model.version,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            evaluation_provider="TruLens",
            temperature=0.0,
            top_p=1.0,
            max_tokens=4096,
        )


def test_candidate_service_lists_candidates_for_experiment() -> None:
    services = _create_services()
    experiment = services["experiment_service"].create_experiment(
        name="support-benchmark",
        description="Compare support assistant variants.",
        owner="governance-team",
    )
    prompt, model, dataset = _create_assets(services)

    first = services["candidate_service"].create_candidate(
        experiment_id=experiment.experiment_id,
        name="Baseline",
        prompt_id=prompt.prompt_id,
        prompt_version=prompt.version,
        model_id=model.model_id,
        model_version=model.version,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        evaluation_provider="TruLens",
        temperature=0.0,
        top_p=1.0,
        max_tokens=4096,
    )
    second = services["candidate_service"].create_candidate(
        experiment_id=experiment.experiment_id,
        name="Higher Temperature",
        prompt_id=prompt.prompt_id,
        prompt_version=prompt.version,
        model_id=model.model_id,
        model_version=model.version,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        evaluation_provider="TruLens",
        temperature=0.2,
        top_p=0.95,
        max_tokens=4096,
    )

    assert services["candidate_service"].list_experiment_candidates(
        experiment.experiment_id
    ) == [first, second]


def test_candidate_service_compares_candidate_configuration() -> None:
    services = _create_services()
    experiment = services["experiment_service"].create_experiment(
        name="support-benchmark",
        description="Compare support assistant variants.",
        owner="governance-team",
    )
    prompt, model, dataset = _create_assets(services)
    alternate_prompt = services["prompt_service"].version_prompt(
        prompt.prompt_id,
        version="v2",
        created_by="prompt-owner",
    )

    baseline = services["candidate_service"].create_candidate(
        experiment_id=experiment.experiment_id,
        name="Baseline",
        prompt_id=prompt.prompt_id,
        prompt_version=prompt.version,
        model_id=model.model_id,
        model_version=model.version,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        evaluation_provider="TruLens",
        temperature=0.0,
        top_p=1.0,
        max_tokens=4096,
        metadata={"tier": "baseline"},
    )
    candidate = services["candidate_service"].create_candidate(
        experiment_id=experiment.experiment_id,
        name="Prompt V2",
        prompt_id=alternate_prompt.prompt_id,
        prompt_version=alternate_prompt.version,
        model_id=model.model_id,
        model_version=model.version,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        evaluation_provider="Phoenix",
        temperature=0.2,
        top_p=0.95,
        max_tokens=8192,
        metadata={"tier": "candidate"},
    )

    comparison = services["candidate_service"].compare_candidate_configuration(
        baseline.candidate_id,
        candidate.candidate_id,
    )

    assert comparison.prompt_id_changed is True
    assert comparison.prompt_version_changed is True
    assert comparison.evaluation_provider_changed is True
    assert comparison.temperature_changed is True
    assert comparison.top_p_changed is True
    assert comparison.max_tokens_changed is True
    assert comparison.metadata_changed is True
    assert comparison.has_changes is True


def _create_services() -> dict[str, object]:
    prompt_repository = InMemoryPromptRepository()
    model_repository = InMemoryModelRepository()
    dataset_repository = InMemoryDatasetRepository()
    experiment_repository = InMemoryExperimentRepository()

    prompt_service = PromptRegistryService(
        prompt_repository=prompt_repository,
        id_generator=_ids(["prompt-1", "prompt-2", "prompt-3"]),
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
    model_service = ModelRegistryService(
        model_repository=model_repository,
        id_generator=_ids(["model-1", "model-2", "model-3"]),
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
    dataset_service = DatasetRegistryService(
        dataset_repository=dataset_repository,
        id_generator=_ids(["dataset-1", "dataset-2", "dataset-3"]),
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
    experiment_service = ExperimentService(
        experiment_repository=experiment_repository,
        id_generator=_ids(["experiment-1", "experiment-2", "experiment-3"]),
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
    candidate_service = ExperimentCandidateService(
        candidate_repository=InMemoryExperimentCandidateRepository(),
        experiment_repository=experiment_repository,
        prompt_repository=prompt_repository,
        model_repository=model_repository,
        dataset_repository=dataset_repository,
        id_generator=_ids(["candidate-1", "candidate-2", "candidate-3"]),
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )

    return {
        "candidate_service": candidate_service,
        "dataset_service": dataset_service,
        "experiment_service": experiment_service,
        "model_service": model_service,
        "prompt_service": prompt_service,
    }


def _create_assets(
    services: dict[str, object],
):
    prompt_service = services["prompt_service"]
    model_service = services["model_service"]
    dataset_service = services["dataset_service"]

    prompt = prompt_service.create_prompt(
        name="claim-validation",
        version="v1",
        template="Answer the claim question.",
        variables=("question",),
        created_by="prompt-owner",
    )
    model = model_service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={"temperature": 0.0},
        context_window=128000,
        creator="model-owner",
    )
    dataset = dataset_service.register_dataset(
        name="claims-benchmark",
        version="2026-06-26",
        description="Insurance claims benchmark.",
        storage_uri="s3://datasets/claims/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1200,
        checksum="sha256:claims-v1",
        creator="data-owner",
    )

    return prompt, model, dataset


def _ids(values: list[str]):
    iterator = iter(values)

    return lambda: next(iterator)
