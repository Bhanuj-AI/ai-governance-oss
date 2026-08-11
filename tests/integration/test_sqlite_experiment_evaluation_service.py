from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.evaluation_dataset import EvaluationDataset
from ai_governance.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation import EvaluationService
from ai_governance.providers.evaluation_provider import EvaluationProvider
from ai_governance.providers.provider_capabilities import ProviderCapabilities
from ai_governance.providers.provider_descriptor import ProviderDescriptor
from ai_governance.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from ai_governance.repositories.sqlite.sqlite_dataset_repository import (
    SQLiteDatasetRepository,
)
from ai_governance.repositories.sqlite.sqlite_evaluation_run_repository import (
    SQLiteEvaluationRunRepository,
)
from ai_governance.repositories.sqlite.sqlite_experiment_candidate_repository import (
    SQLiteExperimentCandidateRepository,
)
from ai_governance.repositories.sqlite.sqlite_experiment_repository import (
    SQLiteExperimentRepository,
)
from ai_governance.repositories.sqlite.sqlite_model_repository import (
    SQLiteModelRepository,
)
from ai_governance.repositories.sqlite.sqlite_prompt_repository import (
    SQLitePromptRepository,
)
from ai_governance.services.dataset_builder import EvaluationDatasetBuilder
from ai_governance.services.datasets import DatasetRegistryService
from ai_governance.services.experiments import (
    ExperimentCandidateService,
    ExperimentEvaluationService,
    ExperimentService,
)
from ai_governance.services.models import ModelRegistryService
from ai_governance.services.prompts import PromptRegistryService
from ai_governance.tenancy.domain import TenantContext


_CONTEXT = TenantContext("org_default", "project_default", "governance-admin", "test-request")


def test_sqlite_experiment_evaluation_service_executes_complete_experiment(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "ai_governance.db")
    database.initialize()

    prompt_repository = SQLitePromptRepository(database)
    model_repository = SQLiteModelRepository(database)
    dataset_repository = SQLiteDatasetRepository(database)
    experiment_repository = SQLiteExperimentRepository(database)
    candidate_repository = SQLiteExperimentCandidateRepository(database)
    run_repository = SQLiteEvaluationRunRepository(database)
    evaluation_repository = InMemoryEvaluationRepository()

    prompt_service = PromptRegistryService(
        prompt_repository=prompt_repository,
        id_generator=lambda: "prompt-1",
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
    model_ids = iter(["model-1", "model-2"])
    model_service = ModelRegistryService(
        model_repository=model_repository,
        id_generator=lambda: next(model_ids),
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
    candidate_ids = iter(["candidate-1", "candidate-2"])
    candidate_service = ExperimentCandidateService(
        candidate_repository=candidate_repository,
        experiment_repository=experiment_repository,
        prompt_repository=prompt_repository,
        model_repository=model_repository,
        dataset_repository=dataset_repository,
        id_generator=lambda: next(candidate_ids),
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
    run_ids = iter(["run-1", "run-2"])
    evaluation_service = ExperimentEvaluationService(
        experiment_service=experiment_service,
        candidate_repository=candidate_repository,
        evaluation_run_repository=run_repository,
        evaluation_repository=evaluation_repository,
        model_repository=model_repository,
        evaluation_service=EvaluationService(
            provider=SQLiteScoredProvider(),
            dataset_builder=EvaluationDatasetBuilder(),
        ),
        workflow_execution_factory=_workflow_execution_factory,
        id_generator=lambda: next(run_ids),
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
        context=_CONTEXT,
    )
    model_a = model_service.register_model(
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={"temperature": 0.0},
        cost={"input_per_1k": 0.01},
        latency=0.4,
        context_window=128000,
        creator="model-owner",
        context=_CONTEXT,
    )
    model_b = model_service.create_model_version(
        model_id=model_a.model_id,
        version="2026-07-01",
        creator="model-owner",
        cost={"input_per_1k": 0.02},
        latency=0.55,
        context=_CONTEXT,
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

    candidate_service.create_candidate(
        experiment_id=experiment.experiment_id,
        name="Baseline",
        prompt_id=prompt.prompt_id,
        prompt_version=prompt.version,
        model_id=model_a.model_id,
        model_version=model_a.version,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        evaluation_provider="TruLens",
        temperature=0.0,
        top_p=1.0,
        max_tokens=4096,
    )
    improved = candidate_service.create_candidate(
        experiment_id=experiment.experiment_id,
        name="Improved",
        prompt_id=prompt.prompt_id,
        prompt_version=prompt.version,
        model_id=model_b.model_id,
        model_version=model_b.version,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        evaluation_provider="TruLens",
        temperature=0.0,
        top_p=1.0,
        max_tokens=4096,
    )

    runs = evaluation_service.execute_experiment(experiment.experiment_id)
    winner = evaluation_service.select_winner(experiment.experiment_id)

    assert len(runs) == 2
    assert winner.candidate == improved
    assert len(run_repository.find_by_experiment_id(experiment.experiment_id)) == 2


class SQLiteScoredProvider(EvaluationProvider):
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="fake",
            display_name="Fake",
            version="1.0",
            adapter_version="1.0.0",
            capabilities=ProviderCapabilities(
                supported_metrics=("quality", "groundedness"),
                supports_artifacts=False,
            ),
        )

    def evaluate(self, dataset: EvaluationDataset) -> EvaluationResult:
        score = 0.82 if dataset.execution_id.endswith("candidate-1") else 0.94

        return EvaluationResult(
            evaluation_id=f"evaluation-{dataset.execution_id}",
            execution_id=dataset.execution_id,
            evaluator_type=self.descriptor.name,
            evaluator_version=self.descriptor.version,
            metrics=[
                EvaluationMetric("QUALITY", score),
                EvaluationMetric("GROUNDEDNESS", score - 0.03),
            ],
            metadata={},
        )

    @property
    def provider_metadata(self) -> dict[str, str]:
        return {"provider": self.descriptor.name}


def _workflow_execution_factory(
    experiment,
    candidate,
    run_id: str,
) -> WorkflowExecution:
    return WorkflowExecution(
        workflow_id=experiment.experiment_id,
        execution_id=f"{run_id}-{candidate.candidate_id}",
        workflow_name=experiment.name,
        workflow_version="experiment-candidate",
        execution_status="COMPLETED",
        input={"candidate_id": candidate.candidate_id},
        final_state={},
        events=[],
    )
