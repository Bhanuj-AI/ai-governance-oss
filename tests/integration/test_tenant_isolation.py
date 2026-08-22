from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.domain.jobs import JobExecutionContext, JobSubmission, JobType
from ai_governance.domain.models import ModelStatus
from ai_governance.ontology import InMemoryOntologyGraphRepository, OntologyEntity
from ai_governance.repositories import InMemoryJobRepository
from ai_governance.repositories.in_memory_model_repository import (
    InMemoryModelRepository,
)
from ai_governance.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)
from ai_governance.repositories.settings_runtime_connection_repository import (
    SettingsRuntimeConnectionRepository,
)
from ai_governance.services.job_submission_service import JobSubmissionService
from ai_governance.services.models import ModelNotFoundError, ModelRegistryService
from ai_governance.services.prompts import PromptRegistryService
from ai_governance.services.runtime_connection_service import RuntimeConnectionService
from ai_governance.settings_control.repository import InMemorySettingsRepository
from ai_governance.tenancy.domain import TenantContext


def _submission(organization_id: str, project_id: str) -> JobSubmission:
    return JobSubmission(
        job_type=JobType.EVALUATION,
        input_refs={"execution_id": "same"},
        idempotency_key="same-key",
        submitted_by="actor",
        execution_context=JobExecutionContext(
            organization_id, project_id, "actor", "request", None
        ),
    )


def test_job_ids_lists_and_idempotency_are_tenant_isolated():
    repository = InMemoryJobRepository()
    ids = iter(("job_a", "job_b"))
    service = JobSubmissionService(repository, id_generator=lambda: next(ids))
    first = service.submit(_submission("org_a", "project_a"))
    second = service.submit(_submission("org_b", "project_b"))
    assert first.job_id != second.job_id
    assert repository.find_by_id("job_a", "org_b", "project_b") is None
    assert repository.list_jobs(organization_id="org_a", project_id="project_a") == [
        first
    ]
    assert repository.list_jobs(organization_id="org_b", project_id="project_b") == [
        second
    ]


def test_ontology_identifiers_are_isolated_by_tenant():
    repository = InMemoryOntologyGraphRepository()
    now = datetime.now(UTC)
    for organization_id, project_id, owner in (
        ("org_a", "project_a", "owner-a"),
        ("org_b", "project_b", "owner-b"),
    ):
        repository.save_entity(
            OntologyEntity(
                entity_id="same-id",
                entity_type="Actor",
                owner=owner,
                lifecycle="ACTIVE",
                created_at=now,
                organization_id=organization_id,
                project_id=project_id,
            )
        )
    assert (
        repository.get_entity("Actor", "same-id", "org_a", "project_a").owner
        == "owner-a"
    )
    assert (
        repository.get_entity("Actor", "same-id", "org_b", "project_b").owner
        == "owner-b"
    )
    assert repository.get_entity("Actor", "same-id", "org_a", "project_b") is None


def test_observed_prompt_and_model_registries_are_tenant_isolated():
    prompt_service = PromptRegistryService(InMemoryPromptRepository())
    model_service = ModelRegistryService(InMemoryModelRepository())
    first = TenantContext("org_a", "project_a", "actor-a", "request-a")
    second = TenantContext("org_b", "project_b", "actor-b", "request-b")

    for context in (first, second):
        prompt_service.observe_prompt(
            name="assistant", version="v1", source_system="runtime", source_reference="same-run",
            template="Answer from context.", content_hash=None, variables=("context",),
            observed_by=context.actor_id, context=context,
        )
        model_service.observe_model(
            provider="openai", model_name="gpt-5", version="2026-08", source_system="runtime",
            source_reference="same-run", parameters={"temperature": 0}, context_window=128000,
            observed_by=context.actor_id, context=context,
        )

    assert [item.organization_id for item in prompt_service.list_prompts(first)] == ["org_a"]
    assert [item.organization_id for item in prompt_service.list_prompts(second)] == ["org_b"]
    assert [item.organization_id for item in model_service.list_models(first)] == ["org_a"]
    assert [item.organization_id for item in model_service.list_models(second)] == ["org_b"]


def test_managed_model_lifecycle_is_tenant_isolated():
    service = ModelRegistryService(InMemoryModelRepository())
    owner = TenantContext("org_a", "project_a", "actor-a", "request-a")
    other_tenant = TenantContext("org_b", "project_b", "actor-b", "request-b")
    model = service.register_model(
        provider="openai",
        model_name="gpt-5",
        version="v1",
        parameters={},
        context_window=128000,
        creator=owner.actor_id,
        context=owner,
    )

    with pytest.raises(ModelNotFoundError):
        service.activate_model_version(model.model_id, other_tenant)

    assert service.get_model(model.model_id, owner).status == ModelStatus.DRAFT


def test_runtime_connections_are_tenant_isolated():
    service = RuntimeConnectionService(
        SettingsRuntimeConnectionRepository(InMemorySettingsRepository()),
        allowed_runtime_providers=lambda _: ("openai",),
        id_generator=lambda: "same-connection-id",
    )
    first = TenantContext("org_a", "project_a", "actor-a", "request-a")
    second = TenantContext("org_b", "project_b", "actor-b", "request-b")

    for context in (first, second):
        service.create(
            display_name="OpenAI",
            provider="openai",
            settings={},
            secret_refs={"api_key": "env://MISSING"},
            enabled=False,
            project_id=context.project_id,
            context=context,
        )

    assert [item.organization_id for item in service.list(first)] == ["org_a"]
    assert [item.organization_id for item in service.list(second)] == ["org_b"]
