from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ai_governance.domain.causal_audit import (
    EvidenceInterventionPolicyStatus,
    ToolEvidenceDescriptor,
)
from ai_governance.domain.replay import ControlledEvidenceStrategy
from ai_governance.repositories.in_memory.in_memory_evidence_intervention_policy_repository import (
    InMemoryEvidenceInterventionPolicyRepository,
)
from ai_governance.services.evidence_intervention_policy_service import (
    EvidenceInterventionPolicyService,
    InterventionPolicyAmbiguous,
)
from ai_governance.services.evidence_interventions import (
    EvidenceInterventionProviderRegistry,
    InMemoryEvidenceValueResolver,
    StructuredJsonEvidenceInterventionProvider,
)
from ai_governance.tenancy.domain import TenantContext


CONTEXT = TenantContext("org-a", "project-a", "operator", "request-a")
NOW = datetime(2026, 8, 22, tzinfo=UTC)
SCHEMA = {"json_schema": {"type": "object"}}


def _service():
    resolver = InMemoryEvidenceValueResolver()
    provider = StructuredJsonEvidenceInterventionProvider(resolver)
    identifiers = iter(("policy-1", "policy-2"))
    return EvidenceInterventionPolicyService(
        InMemoryEvidenceInterventionPolicyRepository(),
        EvidenceInterventionProviderRegistry((provider,)),
        clock=lambda: NOW,
        id_generator=lambda: next(identifiers),
    )


def test_active_version_is_immutable_and_edit_creates_new_draft():
    service = _service()
    draft = service.create_draft(
        tool_name="risk.lookup",
        schema_id="risk",
        schema_version="1",
        provider_id="structured-json",
        provider_version="v1",
        allowed_strategies=(ControlledEvidenceStrategy.NULLIFY,),
        strategy_configuration={**SCHEMA, "neutral_value": {"records": []}},
        context=CONTEXT,
    )
    active = service.activate(draft.policy_id, draft.version, CONTEXT)
    assert active.status is EvidenceInterventionPolicyStatus.ACTIVE
    with pytest.raises(ValueError, match="immutable"):
        service._repository.save(
            replace(
                active,
                strategy_configuration={
                    **SCHEMA,
                    "neutral_value": {"records": ["bad"]},
                },
                policy_digest="",
            )
        )
    edited = service.create_next_draft(
        active.policy_id,
        active.version,
        {**SCHEMA, "neutral_value": {"records": ["revised"]}},
        CONTEXT,
    )
    assert edited.version == 2
    assert edited.status is EvidenceInterventionPolicyStatus.DRAFT
    assert (
        service.get(active.policy_id, 1, CONTEXT).policy_digest == active.policy_digest
    )
    assert (
        service.retire(active.policy_id, 1, CONTEXT).status
        is EvidenceInterventionPolicyStatus.RETIRED
    )


def test_exact_active_selector_resolves_and_ambiguity_fails_closed():
    service = _service()
    draft = service.create_draft(
        tool_name="risk.lookup",
        schema_id="risk",
        schema_version="1",
        provider_id="structured-json",
        provider_version="v1",
        allowed_strategies=(ControlledEvidenceStrategy.NULLIFY,),
        strategy_configuration={**SCHEMA, "neutral_value": {"records": []}},
        context=CONTEXT,
    )
    service.activate(draft.policy_id, 1, CONTEXT)
    descriptor = ToolEvidenceDescriptor(
        "call",
        "risk.lookup",
        "artifact://risk",
        "sha256:x",
        "application/json",
        "risk",
        "1",
        "adapter",
    )
    assert (
        service.resolve_active(
            descriptor, ControlledEvidenceStrategy.NULLIFY, CONTEXT
        ).policy_id
        == "policy-1"
    )
    duplicate = service.create_draft(
        tool_name="risk.lookup",
        schema_id="risk",
        schema_version="1",
        provider_id="structured-json",
        provider_version="v1",
        allowed_strategies=(ControlledEvidenceStrategy.NULLIFY,),
        strategy_configuration={**SCHEMA, "neutral_value": {"records": []}},
        context=CONTEXT,
    )
    with pytest.raises(InterventionPolicyAmbiguous):
        service.activate(duplicate.policy_id, duplicate.version, CONTEXT)


def test_second_version_cannot_be_active_while_prior_version_is_active():
    service = _service()
    draft = service.create_draft(
        tool_name="risk.lookup",
        schema_id="risk",
        schema_version="1",
        provider_id="structured-json",
        provider_version="v1",
        allowed_strategies=(ControlledEvidenceStrategy.NULLIFY,),
        strategy_configuration={**SCHEMA, "neutral_value": {"records": []}},
        context=CONTEXT,
    )
    active = service.activate(draft.policy_id, 1, CONTEXT)
    next_draft = service.create_next_draft(
        active.policy_id,
        active.version,
        {**SCHEMA, "neutral_value": {"records": ["new"]}},
        CONTEXT,
    )
    with pytest.raises(InterventionPolicyAmbiguous):
        service.activate(next_draft.policy_id, next_draft.version, CONTEXT)
