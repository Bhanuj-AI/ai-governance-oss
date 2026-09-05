"""Dependency wiring for operator-governed counterfactual policies."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from ai_governance.services.evidence_intervention_policy_service import (
    EvidenceInterventionPolicyService,
)
from ai_governance.services.evidence_interventions import (
    EvidenceInterventionProviderRegistry,
    GovernedCounterfactualGenerator,
    InMemoryEvidenceValueResolver,
    OpaqueReferenceEvidenceInterventionProvider,
    StructuredJsonEvidenceInterventionProvider,
)


@dataclass(frozen=True)
class EvidenceInterventionRuntime:
    resolver: InMemoryEvidenceValueResolver
    providers: EvidenceInterventionProviderRegistry
    policies: EvidenceInterventionPolicyService
    generator: GovernedCounterfactualGenerator


@lru_cache(maxsize=1)
def get_evidence_intervention_runtime() -> EvidenceInterventionRuntime:
    """Compose the bounded local resolver used by the reference runtime.

    Production runtime plugins replace this dependency with an adapter-owned,
    tenant-authorized resolver. The control plane never stores raw evidence.
    """
    from ai_governance.api.dependencies.repositories import (
        get_evidence_intervention_policy_repository,
    )

    resolver = InMemoryEvidenceValueResolver()
    if os.getenv("AI_GOVERNANCE_ENV", "").strip().lower() in {
        "local",
        "development",
        "test",
    }:
        from ai_governance.api.demo_agent_runtime import register_local_demo_evidence

        register_local_demo_evidence(resolver)
    providers = EvidenceInterventionProviderRegistry(
        (
            StructuredJsonEvidenceInterventionProvider(resolver),
            OpaqueReferenceEvidenceInterventionProvider(),
        )
    )
    policies = EvidenceInterventionPolicyService(
        get_evidence_intervention_policy_repository(), providers
    )
    return EvidenceInterventionRuntime(
        resolver,
        providers,
        policies,
        GovernedCounterfactualGenerator(policies, providers, resolver),
    )


@lru_cache(maxsize=1)
def get_evidence_intervention_policy_service() -> EvidenceInterventionPolicyService:
    """Return the policy lifecycle service.

    The bundled JSON provider validates declarative policy configuration. Runtime
    integrations supply their authorized evidence resolver when composing the
    Causal Audit worker; this API service never resolves or persists evidence.
    """
    return get_evidence_intervention_runtime().policies


def get_governed_counterfactual_generator() -> GovernedCounterfactualGenerator:
    return get_evidence_intervention_runtime().generator
