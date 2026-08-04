from datetime import UTC, datetime

from kavach.decisions import (
    DecisionEvidenceReference,
    DecisionPolicyReference,
    DecisionProducerType,
    DecisionProvenance,
    DecisionSupersession,
    DecisionTarget,
    DecisionTargetType,
    GovernanceDecision,
)
from kavach.ontology import (
    EntityType,
    InMemoryOntologyGraphRepository,
    OntologyService,
    RelationshipType,
)
from kavach.ontology.synchronization import (
    GovernanceDecisionOntologySynchronizer,
    GovernanceDecisionProjection,
    GovernanceInsightOntologySynchronizer,
)
from kavach.services.governance_insights import GovernanceInsight


def test_governance_decision_synchronization_links_target_and_approval() -> None:
    service = OntologyService(InMemoryOntologyGraphRepository())
    service.create_entity(
        entity_id="candidate-1",
        entity_type=EntityType.CANDIDATE,
        owner="experiment-1",
        lifecycle="CREATED",
    )
    decision = GovernanceDecisionProjection(
        decision_id="decision-1",
        decision_type="PROMOTE",
        target_entity_type=EntityType.CANDIDATE.value,
        target_entity_id="candidate-1",
        status="APPROVED",
        reason="Best score",
        created_by="reviewer",
        approved_by="reviewer",
        created_at=datetime(2026, 6, 30, tzinfo=UTC),
    )

    result = GovernanceDecisionOntologySynchronizer(service).synchronize(
        decision
    )

    assert result.succeeded is True
    assert service.find_relationships(
        "GovernanceDecision",
        "decision-1",
        direction="outgoing",
        relationship_type=RelationshipType.DECIDES_ON.value,
    )
    assert service.find_relationships(
        "GovernanceDecision",
        "decision-1",
        direction="outgoing",
        relationship_type=RelationshipType.APPROVED_BY.value,
    )


def test_governance_decision_synchronization_accepts_domain_decision() -> None:
    service = OntologyService(InMemoryOntologyGraphRepository())
    service.create_entity(
        entity_id="candidate-1",
        entity_type=EntityType.CANDIDATE,
        owner="experiment-1",
        lifecycle="CREATED",
    )
    service.create_entity(
        entity_id="evaluation-result-1",
        entity_type=EntityType.EVALUATION_RESULT,
        owner="evaluation-service",
        lifecycle="COMPLETED",
    )
    service.create_entity(
        entity_id="policy-1",
        entity_type=EntityType.POLICY,
        owner="governance",
        lifecycle="ACTIVE",
    )
    service.create_entity(
        entity_id="decision-0",
        entity_type=EntityType.GOVERNANCE_DECISION,
        owner="policy-engine-1",
        lifecycle="SUPERSEDED",
    )
    decision = GovernanceDecision.approved(
        decision_id="decision-1",
        target=DecisionTarget(
            target_type=DecisionTargetType.CANDIDATE,
            target_id="candidate-1",
        ),
        reason="Candidate passed governance.",
        evidence=(
            DecisionEvidenceReference(
                evidence_type=EntityType.EVALUATION_RESULT.value,
                evidence_id="evaluation-result-1",
            ),
        ),
        policies=(
            DecisionPolicyReference(
                policy_id="policy-1",
                policy_version="2026-07-02",
                policy_name="minimum-quality-gate",
            ),
        ),
        provenance=DecisionProvenance(
            producer_type=DecisionProducerType.POLICY_ENGINE,
            producer_id="policy-engine-1",
            actor_id="governance-admin",
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        ),
        supersession=DecisionSupersession(
            supersedes_decision_id="decision-0",
        ),
        finalized_at=datetime(2026, 7, 2, 1, tzinfo=UTC),
    )

    result = GovernanceDecisionOntologySynchronizer(service).synchronize(
        decision
    )

    assert result.succeeded is True
    for relationship_type in (
        RelationshipType.DECIDES_ON,
        RelationshipType.GENERATED_FROM,
        RelationshipType.GOVERNED_BY,
        RelationshipType.APPROVED_BY,
        RelationshipType.SUPERSEDES,
    ):
        assert service.find_relationships(
            "GovernanceDecision",
            "decision-1",
            direction="outgoing",
            relationship_type=relationship_type.value,
        )


def test_governance_insight_synchronization_recommends_candidate() -> None:
    service = OntologyService(InMemoryOntologyGraphRepository())
    service.create_entity(
        entity_id="candidate-1",
        entity_type=EntityType.CANDIDATE,
        owner="experiment-1",
        lifecycle="CREATED",
    )
    insight = GovernanceInsight(
        summary="Candidate is currently recommended.",
        status="SUCCEEDED",
        confidence="HIGH",
        related_resources=[{"candidate_id": "candidate-1"}],
        generated_at=datetime(2026, 6, 30, tzinfo=UTC),
    )

    result = GovernanceInsightOntologySynchronizer(service).synchronize(insight)

    assert result.succeeded is True
    insight_id = result.synchronized_entity_ids[0]
    assert service.find_relationships(
        "GovernanceInsight",
        insight_id,
        direction="outgoing",
        relationship_type=RelationshipType.RECOMMENDS.value,
    )
