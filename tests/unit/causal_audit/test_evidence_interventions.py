from datetime import UTC, datetime

import pytest

from ai_governance.domain.causal_audit import (
    EvidenceInterventionPolicy,
    EvidenceInterventionPolicyStatus,
    ToolEvidenceDescriptor,
)
from ai_governance.domain.replay import ControlledEvidenceStrategy
from ai_governance.services.evidence_interventions import (
    InMemoryEvidenceValueResolver,
    NoEffectiveIntervention,
    OpaqueReferenceEvidenceInterventionProvider,
    StructuredJsonEvidenceInterventionProvider,
)
from ai_governance.tenancy.domain import TenantContext

CONTEXT = TenantContext("org-a", "project-a", "operator", "request-a")
NOW = datetime(2026, 8, 22, tzinfo=UTC)


def _policy(strategy, configuration):
    configuration = {"json_schema": {"type": "object"}, **configuration}
    return EvidenceInterventionPolicy(
        "policy-1",
        1,
        "org-a",
        "project-a",
        EvidenceInterventionPolicyStatus.ACTIVE,
        "risk.lookup",
        "risk-schema",
        "1",
        "structured-json",
        "v1",
        (strategy,),
        configuration,
        NOW,
        "operator",
        NOW,
        "operator",
    )


def _descriptor():
    return ToolEvidenceDescriptor(
        "call-1",
        "risk.lookup",
        "artifact://original",
        "sha256:original",
        "application/json",
        "risk-schema",
        "1",
        "deterministic-agent-runtime/v1",
    )


def _provider():
    resolver = InMemoryEvidenceValueResolver(
        {
            ("org-a", "project-a", "artifact://original"): {
                "risk_score": 0.8,
                "records": ["one"],
            },
            ("org-a", "project-a", "artifact://clean"): {
                "risk_score": 0.1,
                "records": [],
            },
        }
    )
    return resolver, StructuredJsonEvidenceInterventionProvider(resolver)


def test_nullify_uses_policy_neutral_value_and_is_deterministic():
    resolver, provider = _provider()
    policy = _policy(
        ControlledEvidenceStrategy.NULLIFY,
        {"neutral_value": {"risk_score": 0.0, "records": []}},
    )
    original = resolver.resolve("artifact://original", CONTEXT)
    _, first = provider.generate(
        original, _descriptor(), policy, ControlledEvidenceStrategy.NULLIFY, 1, CONTEXT
    )
    _, second = provider.generate(
        original, _descriptor(), policy, ControlledEvidenceStrategy.NULLIFY, 1, CONTEXT
    )
    assert first.counterfactual_evidence_digest == second.counterfactual_evidence_digest


def test_replace_selects_reference_deterministically():
    resolver, provider = _provider()
    policy = _policy(
        ControlledEvidenceStrategy.REPLACE,
        {"replacement_references": ["artifact://clean"]},
    )
    _, result = provider.generate(
        resolver.resolve("artifact://original", CONTEXT),
        _descriptor(),
        policy,
        ControlledEvidenceStrategy.REPLACE,
        7,
        CONTEXT,
    )
    assert result.counterfactual_evidence_digest != result.original_evidence_digest
    assert result.counterfactual_evidence_ref.startswith("counterfactual:sha256:")


def test_perturb_enforces_constraints():
    resolver, provider = _provider()
    policy = _policy(
        ControlledEvidenceStrategy.PERTURB,
        {
            "operations": [
                {
                    "path": "/risk_score",
                    "operation": "NUMERIC_DELTA",
                    "delta": -0.5,
                    "minimum": 0,
                }
            ]
        },
    )
    altered, _ = provider.generate(
        resolver.resolve("artifact://original", CONTEXT),
        _descriptor(),
        policy,
        ControlledEvidenceStrategy.PERTURB,
        3,
        CONTEXT,
    )
    assert altered["risk_score"] == pytest.approx(0.3)


def test_identical_counterfactual_is_rejected():
    resolver, provider = _provider()
    policy = _policy(
        ControlledEvidenceStrategy.PERTURB,
        {"operations": [{"path": "/risk_score", "operation": "SET", "value": 0.8}]},
    )
    with pytest.raises(NoEffectiveIntervention):
        provider.generate(
            resolver.resolve("artifact://original", CONTEXT),
            _descriptor(),
            policy,
            ControlledEvidenceStrategy.PERTURB,
            3,
            CONTEXT,
        )


def test_opaque_reference_provider_never_materialises_external_evidence():
    provider = OpaqueReferenceEvidenceInterventionProvider()
    descriptor = ToolEvidenceDescriptor(
        "call-1",
        "risk.lookup",
        "synthetic://evidence/run/1",
        "sha256:original",
        "application/vnd.synthetic-agent-runtime.evidence+json",
        "risk-schema",
        "1",
        "synthetic-agent-runtime/v1",
        {},
    )
    policy = EvidenceInterventionPolicy(
        "policy-opaque",
        1,
        "org-a",
        "project-a",
        EvidenceInterventionPolicyStatus.ACTIVE,
        "risk.lookup",
        "risk-schema",
        "1",
        "opaque-reference",
        "v1",
        (ControlledEvidenceStrategy.REPLACE,),
        {
            "counterfactual_reference_namespace": "synthetic://counterfactual",
            "runtime_attests_validation": True,
        },
        NOW,
        "operator",
        NOW,
        "operator",
    )

    result = provider.generate_reference_only(
        descriptor, policy, ControlledEvidenceStrategy.REPLACE, 7, CONTEXT
    )

    assert result.counterfactual_evidence_ref.startswith("synthetic://counterfactual:")
    assert result.counterfactual_evidence_digest != descriptor.evidence_digest
