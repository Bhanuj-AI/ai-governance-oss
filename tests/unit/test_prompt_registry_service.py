from datetime import UTC, datetime

import pytest

from kavach.domain.prompts import PromptStatus
from kavach.domain.assets import AssetProvenance
from kavach.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)
from kavach.services.prompts import (
    PromptLifecycleError,
    PromptRegistryService,
    PromptVersionConflictError,
)


def test_prompt_registry_creates_prompt() -> None:
    service = _create_service()

    prompt = service.create_prompt(
        name="claim-decision",
        version="1.0.0",
        template="Classify claim: {{claim_text}}",
        variables=["claim_text"],
        created_by="governance-admin",
    )

    assert prompt.prompt_id == "prompt-1"
    assert prompt.name == "claim-decision"
    assert prompt.version == "1.0.0"
    assert prompt.variables == ("claim_text",)
    assert prompt.created_at == datetime(2026, 6, 25, tzinfo=UTC)
    assert prompt.created_by == "governance-admin"
    assert prompt.status == PromptStatus.DRAFT


def test_prompt_registry_rejects_duplicate_prompt_version() -> None:
    service = _create_service()
    service.create_prompt(
        name="claim-decision",
        version="1.0.0",
        template="Classify claim: {{claim_text}}",
        variables=["claim_text"],
        created_by="governance-admin",
    )

    with pytest.raises(PromptVersionConflictError):
        service.create_prompt(
            name="claim-decision",
            version="1.0.0",
            template="Classify claim again: {{claim_text}}",
            variables=["claim_text"],
            created_by="governance-admin",
        )


def test_prompt_registry_versions_prompt() -> None:
    service = _create_service()
    original = service.create_prompt(
        name="claim-decision",
        version="1.0.0",
        template="Classify claim: {{claim_text}}",
        variables=["claim_text"],
        created_by="governance-admin",
    )

    versioned = service.version_prompt(
        prompt_id=original.prompt_id,
        version="2.0.0",
        template="Classify claim: {{claim_text}}\nExplain: {{policy_text}}",
        variables=["claim_text", "policy_text"],
        created_by="prompt-owner",
    )

    assert versioned.prompt_id == "prompt-2"
    assert versioned.name == original.name
    assert versioned.version == "2.0.0"
    assert versioned.status == PromptStatus.DRAFT
    assert versioned.variables == ("claim_text", "policy_text")


def test_prompt_registry_diffs_prompts() -> None:
    service = _create_service()
    original = service.create_prompt(
        name="claim-decision",
        version="1.0.0",
        template="Classify claim: {{claim_text}}",
        variables=["claim_text"],
        created_by="governance-admin",
    )
    candidate = service.version_prompt(
        prompt_id=original.prompt_id,
        version="2.0.0",
        template="Classify claim: {{claim_text}}\nUse policy: {{policy_text}}",
        variables=["claim_text", "policy_text"],
        created_by="prompt-owner",
    )

    diff = service.diff_prompts(
        baseline_prompt_id=original.prompt_id,
        candidate_prompt_id=candidate.prompt_id,
    )

    assert diff.baseline_prompt_id == original.prompt_id
    assert diff.candidate_prompt_id == candidate.prompt_id
    assert diff.template_changed is True
    assert diff.variables_added == ("policy_text",)
    assert diff.variables_removed == ()
    assert any(
        line == "+Use policy: {{policy_text}}"
        for line in diff.unified_template_diff
    )


def test_prompt_registry_activates_prompt_and_deprecates_previous_active() -> None:
    service = _create_service()
    original = service.create_prompt(
        name="claim-decision",
        version="1.0.0",
        template="Classify claim: {{claim_text}}",
        variables=["claim_text"],
        created_by="governance-admin",
    )
    candidate = service.version_prompt(
        prompt_id=original.prompt_id,
        version="2.0.0",
        created_by="prompt-owner",
    )

    activated_original = service.activate_prompt(original.prompt_id)
    activated_candidate = service.activate_prompt(candidate.prompt_id)

    assert activated_original.status == PromptStatus.ACTIVE
    assert activated_candidate.status == PromptStatus.ACTIVE
    assert service.get_prompt(original.prompt_id).status == PromptStatus.DEPRECATED
    assert service.get_prompt(candidate.prompt_id).status == PromptStatus.ACTIVE


def test_prompt_registry_archives_prompt() -> None:
    service = _create_service()
    prompt = service.create_prompt(
        name="claim-decision",
        version="1.0.0",
        template="Classify claim: {{claim_text}}",
        variables=["claim_text"],
        created_by="governance-admin",
    )

    archived = service.archive_prompt(prompt.prompt_id)

    assert archived.status == PromptStatus.ARCHIVED
    assert service.get_prompt(prompt.prompt_id).status == PromptStatus.ARCHIVED


def test_prompt_registry_rejects_activation_of_archived_prompt() -> None:
    service = _create_service()
    prompt = service.create_prompt(
        name="claim-decision",
        version="1.0.0",
        template="Classify claim: {{claim_text}}",
        variables=["claim_text"],
        created_by="governance-admin",
    )
    service.archive_prompt(prompt.prompt_id)

    with pytest.raises(PromptLifecycleError):
        service.activate_prompt(prompt.prompt_id)


def test_prompt_registry_observes_withheld_content_idempotently() -> None:
    service = _create_service()

    observed = service.observe_prompt(
        name="support-assistant",
        version="v7",
        source_system="evaluation-sdk",
        source_reference="run-123",
        template=None,
        content_hash="sha256:abc123",
        variables=["question"],
        observed_by="runtime-agent",
    )
    repeated = service.observe_prompt(
        name="support-assistant",
        version="v7",
        source_system="evaluation-sdk",
        source_reference="run-123",
        template=None,
        content_hash="sha256:abc123",
        variables=["question"],
        observed_by="runtime-agent",
    )

    assert observed.provenance == AssetProvenance.OBSERVED
    assert observed.content_available is False
    assert observed.template is None
    assert observed.source_system == "evaluation-sdk"
    assert repeated == observed


def test_prompt_registry_rejects_conflicting_observed_evidence() -> None:
    service = _create_service()
    service.observe_prompt(
        name="support-assistant",
        version="v7",
        source_system="evaluation-sdk",
        source_reference="run-123",
        template="Answer using context.",
        content_hash=None,
        variables=[],
        observed_by="runtime-agent",
    )

    with pytest.raises(PromptVersionConflictError):
        service.observe_prompt(
            name="support-assistant",
            version="v7",
            source_system="evaluation-sdk",
            source_reference="run-123",
            template="Answer differently.",
            content_hash=None,
            variables=[],
            observed_by="runtime-agent",
        )


def _create_service() -> PromptRegistryService:
    ids = iter(["prompt-1", "prompt-2", "prompt-3"])

    return PromptRegistryService(
        prompt_repository=InMemoryPromptRepository(),
        id_generator=lambda: next(ids),
        clock=lambda: datetime(2026, 6, 25, tzinfo=UTC),
    )
