from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.domain.evaluation_dataset import EvaluationDataset
from ai_governance.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.domain.experiments import (
    EvaluationRunStatus,
)
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation import EvaluationService
from ai_governance.providers.evaluation_provider import EvaluationProvider
from ai_governance.providers.provider_capabilities import ProviderCapabilities
from ai_governance.providers.provider_descriptor import ProviderDescriptor
from ai_governance.repositories.in_memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from ai_governance.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from ai_governance.repositories.in_memory_evaluation_run_repository import (
    InMemoryEvaluationRunRepository,
)
from ai_governance.repositories.in_memory_experiment_candidate_repository import (
    InMemoryExperimentCandidateRepository,
)
from ai_governance.repositories.in_memory_experiment_repository import (
    InMemoryExperimentRepository,
)
from ai_governance.repositories.in_memory_model_repository import (
    InMemoryModelRepository,
)
from ai_governance.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)
from ai_governance.services.dataset_builder import EvaluationDatasetBuilder
from ai_governance.services.datasets import DatasetRegistryService
from ai_governance.services.experiments import (
    ExperimentCandidateService,
    ExperimentEvaluationError,
    ExperimentEvaluationService,
    ExperimentService,
)
from ai_governance.services.models import ModelRegistryService
from ai_governance.services.prompts import PromptRegistryService
from ai_governance.tenancy.domain import TenantContext

_CONTEXT = TenantContext("org_default", "project_default", "governance-admin", "test-request")


def test_experiment_evaluation_service_executes_candidates_and_selects_winner() -> None:
    services = _create_services()
    experiment = services["experiment_service"].create_experiment(
        name="support-benchmark",
        description="Compare support variants.",
        owner="governance-team",
    )
    prompt, model_a, dataset = _create_shared_assets(services)
    model_b = services["model_service"].create_model_version(
        model_id=model_a.model_id,
        version="2026-07-01",
        creator="model-owner",
        cost={"input_per_1k": 0.03},
        latency=0.6,
        context=_CONTEXT,
    )
    services["candidate_service"].create_candidate(
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
    model_b = services["model_service"].activate_model_version(
        model_b.model_id,
        _CONTEXT,
    )
    candidate = services["candidate_service"].create_candidate(
        experiment_id=experiment.experiment_id,
        name="Candidate",
        prompt_id=prompt.prompt_id,
        prompt_version=prompt.version,
        model_id=model_b.model_id,
        model_version=model_b.version,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        evaluation_provider="TruLens",
        temperature=0.1,
        top_p=0.95,
        max_tokens=4096,
    )

    runs = services["experiment_evaluation_service"].execute_experiment(
        experiment.experiment_id
    )
    winner = services["experiment_evaluation_service"].select_winner(
        experiment.experiment_id
    )
    comparisons = services[
        "experiment_evaluation_service"
    ].compare_experiment_candidates(experiment.experiment_id)

    assert len(runs) == 2
    assert all(run.status == EvaluationRunStatus.COMPLETED for run in runs)
    assert winner.candidate.candidate_id == candidate.candidate_id
    assert winner.rank == 1
    assert len(comparisons) == 1
    assert comparisons[0].winner == candidate
    assert comparisons[0].cost_delta == pytest.approx(-0.02)
    assert comparisons[0].latency_delta == pytest.approx(-0.2)


def test_experiment_evaluation_service_rejects_mixed_dataset_versions() -> None:
    services = _create_services()
    experiment = services["experiment_service"].create_experiment(
        name="support-benchmark",
        description="Compare support variants.",
        owner="governance-team",
    )
    prompt, model, dataset = _create_shared_assets(services)
    second_dataset = services["dataset_service"].create_dataset_version(
        dataset_id=dataset.dataset_id,
        version="2026-07-01",
        checksum="sha256:claims-v2",
        creator="data-owner",
    )
    second_dataset = services["dataset_service"].freeze_dataset(
        second_dataset.dataset_id
    )

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
    services["candidate_service"].create_candidate(
        experiment_id=experiment.experiment_id,
        name="Different Dataset",
        prompt_id=prompt.prompt_id,
        prompt_version=prompt.version,
        model_id=model.model_id,
        model_version=model.version,
        dataset_id=second_dataset.dataset_id,
        dataset_version=second_dataset.version,
        evaluation_provider="TruLens",
        temperature=0.1,
        top_p=0.95,
        max_tokens=4096,
    )

    with pytest.raises(ExperimentEvaluationError):
        services["experiment_evaluation_service"].execute_experiment(
            experiment.experiment_id
        )


def test_experiment_evaluation_service_marks_experiment_failed_when_run_fails() -> None:
    services = _create_services(
        provider=FailingEvaluationProvider(),
    )
    experiment = services["experiment_service"].create_experiment(
        name="support-benchmark",
        description="Compare support variants.",
        owner="governance-team",
    )
    prompt, model, dataset = _create_shared_assets(services)
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

    runs = services["experiment_evaluation_service"].execute_experiment(
        experiment.experiment_id
    )
    refreshed = services["experiment_service"].get_experiment(
        experiment.experiment_id
    )

    assert runs[0].status == EvaluationRunStatus.FAILED
    assert refreshed.status.value == "FAILED"


class ScoredEvaluationProvider(EvaluationProvider):
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
                EvaluationMetric(
                    metric_name="QUALITY",
                    metric_value=score,
                ),
                EvaluationMetric(
                    metric_name="GROUNDEDNESS",
                    metric_value=score - 0.04,
                ),
            ],
            metadata={},
        )

    @property
    def provider_metadata(self) -> dict[str, str]:
        return {"provider": self.descriptor.name}


class FailingEvaluationProvider(EvaluationProvider):
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
        raise RuntimeError(f"boom: {dataset.execution_id}")

    @property
    def provider_metadata(self) -> dict[str, str]:
        return {"provider": self.descriptor.name}


def _create_services(
    provider: EvaluationProvider | None = None,
) -> dict[str, object]:
    prompt_repository = InMemoryPromptRepository()
    model_repository = InMemoryModelRepository()
    dataset_repository = InMemoryDatasetRepository()
    experiment_repository = InMemoryExperimentRepository()
    candidate_repository = InMemoryExperimentCandidateRepository()
    evaluation_repository = InMemoryEvaluationRepository()
    evaluation_run_repository = InMemoryEvaluationRunRepository()

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
        candidate_repository=candidate_repository,
        experiment_repository=experiment_repository,
        prompt_repository=prompt_repository,
        model_repository=model_repository,
        dataset_repository=dataset_repository,
        id_generator=_ids(["candidate-1", "candidate-2", "candidate-3"]),
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
    experiment_evaluation_service = ExperimentEvaluationService(
        experiment_service=experiment_service,
        candidate_repository=candidate_repository,
        evaluation_run_repository=evaluation_run_repository,
        evaluation_repository=evaluation_repository,
        model_repository=model_repository,
        evaluation_service=EvaluationService(
            provider=provider or ScoredEvaluationProvider(),
            dataset_builder=EvaluationDatasetBuilder(),
        ),
        workflow_execution_factory=_workflow_execution_factory,
        id_generator=_ids(["run-1", "run-2", "run-3"]),
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )

    return {
        "candidate_service": candidate_service,
        "dataset_service": dataset_service,
        "experiment_evaluation_service": experiment_evaluation_service,
        "experiment_service": experiment_service,
        "model_service": model_service,
        "prompt_service": prompt_service,
    }


def _create_shared_assets(
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
        context=_CONTEXT,
    )
    prompt = prompt_service.activate_prompt(prompt.prompt_id, _CONTEXT)
    model = model_service.register_model(
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
    model = model_service.activate_model_version(model.model_id, _CONTEXT)
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
    dataset = dataset_service.promote_dataset(dataset.dataset_id)

    return prompt, model, dataset


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


def _ids(values: list[str]):
    iterator = iter(values)

    return lambda: next(iterator)
