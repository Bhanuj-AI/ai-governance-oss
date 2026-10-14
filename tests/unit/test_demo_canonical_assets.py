from hashlib import sha256

from fastapi import FastAPI

from ai_governance.api import demo_seed
from ai_governance.api.demo_canonical_assets import seed_canonical_impact_demo_assets
from ai_governance.api.dependencies.events import get_event_publisher
from ai_governance.api.dependencies.ontology import get_ontology_sync_event_publisher
from ai_governance.api.dependencies.settings_control import get_configuration_service
from ai_governance.demo_assets import (
    DEMO_ASSET_MANIFEST_VERSION,
    IMPACT_DEMO_SCENARIOS,
    impact_demo_assets,
)
from ai_governance.repositories.in_memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from ai_governance.repositories.in_memory_model_repository import (
    InMemoryModelRepository,
)
from ai_governance.repositories.in_memory_policy_administration_repository import (
    InMemoryPolicyAdministrationRepository,
)
from ai_governance.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)
from ai_governance.services.datasets.dataset_registry_service import (
    DatasetRegistryService,
)
from ai_governance.services.models.model_registry_service import ModelRegistryService
from ai_governance.services.policies.policy_administration_service import (
    PolicyAdministrationService,
)
from ai_governance.services.prompts.prompt_registry_service import PromptRegistryService
from ai_governance.tenancy.domain import TenantContext


def test_canonical_impact_demo_assets_are_persisted_idempotently() -> None:
    context = TenantContext(
        "impact-demo-org", "impact-demo-project", "demo-seed", "test"
    )
    models = ModelRegistryService(InMemoryModelRepository())
    prompts = PromptRegistryService(InMemoryPromptRepository())
    datasets = DatasetRegistryService(InMemoryDatasetRepository())
    policies = PolicyAdministrationService(InMemoryPolicyAdministrationRepository())

    created = seed_canonical_impact_demo_assets(
        models=models,
        prompts=prompts,
        datasets=datasets,
        policies=policies,
        context=context,
    )

    assert len(created) == len(IMPACT_DEMO_SCENARIOS) * 6
    assert (
        seed_canonical_impact_demo_assets(
            models=models,
            prompts=prompts,
            datasets=datasets,
            policies=policies,
            context=context,
        )
        == ()
    )

    for slug in IMPACT_DEMO_SCENARIOS:
        manifest = impact_demo_assets(slug)
        model = models.get_model(manifest.model_version_id, context)
        baseline_model = models.get_model(manifest.model_baseline_version_id, context)
        prompt = prompts.get_prompt(manifest.prompt_version_id, context)
        baseline_prompt = prompts.get_prompt(
            manifest.prompt_baseline_version_id, context
        )
        dataset = datasets.get_dataset(manifest.dataset_version_id, context)
        policy = policies.get_policy_version(
            manifest.policy_id, manifest.policy_version
        )
        policy_detail = policies.get_policy_detail(manifest.policy_id)
        policy_definition = policies.get_policy_definition(manifest.policy_id)

        assert (model.model_id, model.model_name, model.version) == (
            manifest.model_version_id,
            manifest.model_id,
            manifest.model_version,
        )
        assert model.provider == manifest.model_provider
        assert (
            baseline_model.model_id,
            baseline_model.model_name,
            baseline_model.version,
        ) == (
            manifest.model_baseline_version_id,
            manifest.model_id,
            manifest.model_baseline_version,
        )
        assert (prompt.prompt_id, prompt.name, prompt.version) == (
            manifest.prompt_version_id,
            manifest.prompt_id,
            manifest.prompt_version,
        )
        assert (
            baseline_prompt.prompt_id,
            baseline_prompt.name,
            baseline_prompt.version,
        ) == (
            manifest.prompt_baseline_version_id,
            manifest.prompt_id,
            manifest.prompt_baseline_version,
        )
        assert prompt.content_hash == (
            f"sha256:{sha256(b'Use supplied evidence and cite the governing policy.').hexdigest()}"
        )
        assert (
            dataset.dataset_id,
            dataset.name,
            dataset.version,
            dataset.checksum,
        ) == (
            manifest.dataset_version_id,
            manifest.dataset_id,
            manifest.dataset_version,
            f"sha256:impact-{slug}-dataset-v1",
        )
        assert (policy.policy_id, policy.version) == (
            manifest.policy_id,
            manifest.policy_version,
        )
        assert policy_detail.metadata["manifest_version"] == DEMO_ASSET_MANIFEST_VERSION
        assert (
            policy_definition.policy_id,
            policy_definition.organization_id,
            policy_definition.project_id,
        ) == (manifest.policy_id, context.organization_id, context.project_id)


def test_startup_seed_builds_policy_service_with_its_normal_dependencies(
    monkeypatch,
) -> None:
    app = FastAPI()
    policy_repository = object()
    event_publisher = object()
    service = object()
    app.dependency_overrides[get_ontology_sync_event_publisher] = lambda: (
        event_publisher
    )

    def _policy_service(repository, publisher):
        assert repository is policy_repository
        assert publisher is event_publisher
        return service

    monkeypatch.setattr(demo_seed, "get_policy_administration_service", _policy_service)

    assert (
        demo_seed._resolve_policy_administration_service(app, policy_repository)
        is service
    )


def test_startup_seed_builds_registry_services_with_normal_dependencies(
    monkeypatch,
) -> None:
    event_publisher = object()
    ontology_publisher = object()
    configuration = object()
    app = FastAPI()
    app.dependency_overrides.update(
        {
            get_event_publisher: lambda: event_publisher,
            get_ontology_sync_event_publisher: lambda: ontology_publisher,
            get_configuration_service: lambda: configuration,
        }
    )
    calls: dict[str, tuple[object, ...]] = {}

    def _model(*args):
        calls["model"] = args
        return "model-service"

    def _prompt(*args):
        calls["prompt"] = args
        return "prompt-service"

    def _dataset(*args):
        calls["dataset"] = args
        return "dataset-service"

    monkeypatch.setattr(demo_seed, "get_model_registry_service", _model)
    monkeypatch.setattr(demo_seed, "get_prompt_registry_service", _prompt)
    monkeypatch.setattr(demo_seed, "get_dataset_registry_service", _dataset)

    model_repository = object()
    prompt_repository = object()
    dataset_repository = object()
    assert (
        demo_seed._resolve_model_registry_service(app, model_repository)
        == "model-service"
    )
    assert (
        demo_seed._resolve_prompt_registry_service(app, prompt_repository)
        == "prompt-service"
    )
    assert (
        demo_seed._resolve_dataset_registry_service(app, dataset_repository)
        == "dataset-service"
    )
    assert calls["model"] == (
        model_repository,
        ontology_publisher,
        event_publisher,
        configuration,
    )
    assert calls["prompt"] == (
        prompt_repository,
        ontology_publisher,
        event_publisher,
    )
    assert calls["dataset"] == (dataset_repository, ontology_publisher)
