from datetime import UTC, datetime
from pathlib import Path

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.repositories.sqlite.sqlite_dataset_repository import (
    SQLiteDatasetRepository,
)
from kavach.repositories.sqlite.sqlite_experiment_candidate_repository import (
    SQLiteExperimentCandidateRepository,
)
from kavach.repositories.sqlite.sqlite_experiment_repository import (
    SQLiteExperimentRepository,
)
from kavach.repositories.sqlite.sqlite_model_repository import (
    SQLiteModelRepository,
)
from kavach.repositories.sqlite.sqlite_prompt_repository import (
    SQLitePromptRepository,
)
from kavach.services.datasets import DatasetRegistryService
from kavach.services.experiments import (
    ExperimentCandidateService,
    ExperimentService,
)
from kavach.services.models import ModelRegistryService
from kavach.services.prompts import PromptRegistryService


def test_sqlite_experiment_candidate_service_persists_candidate(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "kavach.db")
    database.initialize()

    prompt_repository = SQLitePromptRepository(database)
    model_repository = SQLiteModelRepository(database)
    dataset_repository = SQLiteDatasetRepository(database)
    experiment_repository = SQLiteExperimentRepository(database)
    candidate_repository = SQLiteExperimentCandidateRepository(database)

    prompt_service = PromptRegistryService(
        prompt_repository=prompt_repository,
        id_generator=lambda: "prompt-1",
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
    model_service = ModelRegistryService(
        model_repository=model_repository,
        id_generator=lambda: "model-1",
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
    dataset_service = DatasetRegistryService(
        dataset_repository=dataset_repository,
        id_generator=lambda: "dataset-1",
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
    experiment_service = ExperimentService(
        experiment_repository=experiment_repository,
        id_generator=lambda: "experiment-1",
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
    candidate_service = ExperimentCandidateService(
        candidate_repository=candidate_repository,
        experiment_repository=experiment_repository,
        prompt_repository=prompt_repository,
        model_repository=model_repository,
        dataset_repository=dataset_repository,
        id_generator=lambda: "candidate-1",
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )

    experiment = experiment_service.create_experiment(
        name="support-benchmark",
        description="Compare support assistant variants.",
        owner="governance-team",
    )
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

    candidate = candidate_service.create_candidate(
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

    reloaded_service = ExperimentCandidateService(
        candidate_repository=candidate_repository,
        experiment_repository=experiment_repository,
        prompt_repository=prompt_repository,
        model_repository=model_repository,
        dataset_repository=dataset_repository,
    )
    reloaded = reloaded_service.get_candidate(candidate.candidate_id)

    assert reloaded.name == "Baseline"
    assert reloaded.evaluation_provider == "TruLens"
    assert reloaded.metadata == {"tier": "baseline"}
