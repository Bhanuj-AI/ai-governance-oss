from datetime import UTC, datetime

from ai_governance.decisions import (
    DecisionEvidenceReference,
    DecisionPolicyReference,
    DecisionProducerType,
    DecisionProvenance,
    DecisionTarget,
    DecisionTargetType,
    GovernanceDecision,
    PolicyEffect,
)
from ai_governance.decisions.evidence_builder import DecisionEvidenceBuilder
from ai_governance.ontology import (
    EntityType,
    InMemoryOntologyGraphQueryRepository,
    InMemoryOntologyGraphRepository,
    OntologyGraphQueryService,
    OntologyService,
)
from ai_governance.ontology.synchronization import (
    GovernanceDecisionOntologySynchronizer,
    PolicyOntologySynchronizer,
)
from ai_governance.repositories import InMemoryPolicyAdministrationRepository
from ai_governance.services.policies import (
    PolicyAdministrationService,
    build_policy_rule,
)


def test_policy_synchronizer_projects_active_policy_identity_and_lifecycle() -> None:
    repository = InMemoryPolicyAdministrationRepository()
    policy_service = PolicyAdministrationService(
        repository,
        id_generator=lambda: "claims-release-gate",
        clock=lambda: datetime(2026, 9, 16, tzinfo=UTC),
    )
    policy_service.create_policy(
        name="Claims release gate",
        description="Approve claims candidates with sufficient relevance.",
        organization_id="org-1",
        project_id="project-1",
        category="PROMPT_SAFETY",
        owner="claims-ai-release-engineering",
        created_by="governance-admin",
        target_types=(DecisionTargetType.CANDIDATE.value,),
        rules=(
            build_policy_rule(
                rule_id="approve-relevant-claims-response",
                name="Approve relevant claims response",
                conditions=(
                    {
                        "field_path": "metrics.answer_relevance.score",
                        "operator": "GREATER_THAN_OR_EQUAL",
                        "expected_value": 0.8,
                    },
                ),
                effect=PolicyEffect.APPROVE.value,
                reason_template="Answer relevance meets the claims threshold.",
                priority=100,
                severity="LOW",
                metadata={},
            ),
        ),
        metadata={},
    )
    policy_service.activate_version(
        policy_id="claims-release-gate",
        version="1",
        activated_by="governance-admin",
    )

    ontology = OntologyService(InMemoryOntologyGraphRepository())
    result = PolicyOntologySynchronizer(ontology, repository).synchronize(
        repository.get_definition("claims-release-gate")
    )

    policy = ontology.get_entity(EntityType.POLICY.value, "claims-release-gate")
    assert result.succeeded is True
    assert policy is not None
    assert policy.lifecycle == "ACTIVE"
    assert policy.immutable_attributes["name"] == "Claims release gate"
    assert policy.mutable_attributes == {
        "status": "ACTIVE",
        "active_version": "1",
        "target_types": ["Candidate"],
        "rule_count": 1,
    }


def test_policy_projection_removes_policy_missing_evidence_from_decision_graph() -> None:
    repository = InMemoryPolicyAdministrationRepository()
    policy_service = PolicyAdministrationService(
        repository,
        id_generator=lambda: "claims-release-gate",
        clock=lambda: datetime(2026, 9, 16, tzinfo=UTC),
    )
    policy_service.create_policy(
        name="Claims release gate",
        description="Approve claims candidates with sufficient relevance.",
        organization_id="org-1",
        project_id="project-1",
        category="PROMPT_SAFETY",
        owner="claims-ai-release-engineering",
        created_by="governance-admin",
        target_types=(DecisionTargetType.CANDIDATE.value,),
        rules=(
            build_policy_rule(
                rule_id="approve-relevant-claims-response",
                name="Approve relevant claims response",
                conditions=(
                    {
                        "field_path": "metrics.answer_relevance.score",
                        "operator": "GREATER_THAN_OR_EQUAL",
                        "expected_value": 0.8,
                    },
                ),
                effect=PolicyEffect.APPROVE.value,
                reason_template="Answer relevance meets the claims threshold.",
                priority=100,
                severity="LOW",
                metadata={},
            ),
        ),
        metadata={},
    )
    policy_service.activate_version(
        policy_id="claims-release-gate",
        version="1",
        activated_by="governance-admin",
    )

    repository_graph = InMemoryOntologyGraphRepository()
    ontology = OntologyService(repository_graph)
    ontology.create_entity(
        entity_id="claims-candidate-v2",
        entity_type=EntityType.CANDIDATE,
        owner="claims-experiment",
        lifecycle="CREATED",
    )
    ontology.create_entity(
        entity_id="claims-evaluation-v2",
        entity_type=EntityType.EVALUATION_RESULT,
        owner="claims-evaluator",
        lifecycle="COMPLETED",
    )
    PolicyOntologySynchronizer(ontology, repository).synchronize(
        repository.get_definition("claims-release-gate")
    )
    GovernanceDecisionOntologySynchronizer(ontology).synchronize(
        GovernanceDecision.approved(
            decision_id="claims-decision-v2",
            target=DecisionTarget(
                target_type=DecisionTargetType.CANDIDATE,
                target_id="claims-candidate-v2",
            ),
            reason="Claims candidate passed the release gate.",
            evidence=(
                DecisionEvidenceReference(
                    evidence_type=EntityType.EVALUATION_RESULT.value,
                    evidence_id="claims-evaluation-v2",
                ),
            ),
            policies=(
                DecisionPolicyReference(
                    policy_id="claims-release-gate",
                    policy_version="1",
                    policy_name="Claims release gate",
                ),
            ),
            provenance=DecisionProvenance(
                producer_type=DecisionProducerType.POLICY_ENGINE,
                producer_id="policy-engine",
                created_at=datetime(2026, 9, 16, tzinfo=UTC),
            ),
        )
    )

    evidence = DecisionEvidenceBuilder(
        OntologyGraphQueryService(InMemoryOntologyGraphQueryRepository(repository_graph))
    ).build_for_target(DecisionTargetType.CANDIDATE, "claims-candidate-v2")

    assert EntityType.POLICY.value in {node.entity_type for node in evidence.nodes}
    assert all(missing.evidence_type != EntityType.POLICY.value for missing in evidence.missing)
