import pytest

from kavach.ontology import (
    Cardinality,
    EntityType,
    InvalidOntologyRelationshipError,
    OntologyRelationship,
    RelationshipType,
    RelationshipValidator,
)


def test_relationship_rules_use_cardinality_enum() -> None:
    rule = RelationshipValidator().rule_for(RelationshipType.USES)

    assert rule.cardinality is Cardinality.MANY_TO_ONE


def test_validator_accepts_valid_candidate_uses_prompt_version() -> None:
    relationship = OntologyRelationship(
        relationship_id="rel-1",
        relationship_type=RelationshipType.USES,
        source_entity_id="candidate-1",
        source_entity_type=EntityType.CANDIDATE,
        target_entity_id="prompt-v1",
        target_entity_type=EntityType.PROMPT_VERSION,
        created_by="tester",
    )

    RelationshipValidator().validate(relationship)


def test_validator_accepts_governance_decision_generated_from_policy() -> None:
    relationship = OntologyRelationship(
        relationship_id="decision-policy-provenance",
        relationship_type=RelationshipType.GENERATED_FROM,
        source_entity_id="decision-1",
        source_entity_type=EntityType.GOVERNANCE_DECISION,
        target_entity_id="policy-1",
        target_entity_type=EntityType.POLICY,
        created_by="policy-engine",
    )

    RelationshipValidator().validate(relationship)


def test_validator_accepts_governance_decision_generated_from_job() -> None:
    relationship = OntologyRelationship(
        relationship_id="decision-job-provenance",
        relationship_type=RelationshipType.GENERATED_FROM,
        source_entity_id="decision-1",
        source_entity_type=EntityType.GOVERNANCE_DECISION,
        target_entity_id="job-1",
        target_entity_type=EntityType.JOB,
        created_by="policy-engine",
    )

    RelationshipValidator().validate(relationship)


@pytest.mark.parametrize(
    ("source_type", "relationship_type", "target_type"),
    [
        (
            EntityType.GOVERNANCE_DECISION,
            RelationshipType.GENERATED_FROM,
            EntityType.METRIC,
        ),
        (
            EntityType.GOVERNANCE_DECISION,
            RelationshipType.GENERATED_FROM,
            EntityType.LEADERBOARD,
        ),
        (
            EntityType.GOVERNANCE_INSIGHT,
            RelationshipType.GENERATED_FROM,
            EntityType.CANDIDATE,
        ),
        (
            EntityType.GOVERNANCE_INSIGHT,
            RelationshipType.GENERATED_FROM,
            EntityType.EXPERIMENT,
        ),
        (
            EntityType.GOVERNANCE_REPORT,
            RelationshipType.GENERATED_FROM,
            EntityType.MCP_AUDIT_RECORD,
        ),
        (EntityType.JOB, RelationshipType.GENERATED_FROM, EntityType.LEADERBOARD),
        (EntityType.JOB, RelationshipType.GENERATED_FROM, EntityType.GOVERNANCE_REPORT),
        (EntityType.REPLAY, RelationshipType.REPLAY_OF, EntityType.WORKFLOW_EXECUTION),
        (EntityType.REPLAY, RelationshipType.PRODUCES, EntityType.EVALUATION_RESULT),
        (
            EntityType.REPLAY,
            RelationshipType.PRODUCES,
            EntityType.EVALUATION_COMPARISON,
        ),
        (EntityType.REPLAY, RelationshipType.CAUSED_DRIFT, EntityType.DRIFT_ANALYSIS),
        (EntityType.REPLAY, RelationshipType.RESULTED_IN, EntityType.REPLAY_RESULT),
        (
            EntityType.REPLAY,
            RelationshipType.GENERATED_FROM,
            EntityType.EVALUATION_RESULT,
        ),
        (
            EntityType.GOVERNANCE_DECISION,
            RelationshipType.DECIDES_ON,
            EntityType.EVALUATION_RESULT,
        ),
        (
            EntityType.GOVERNANCE_DECISION,
            RelationshipType.DECIDES_ON,
            EntityType.GOVERNANCE_DECISION,
        ),
    ],
)
def test_validator_accepts_all_synchronizer_specific_contract_extensions(
    source_type: EntityType,
    relationship_type: RelationshipType,
    target_type: EntityType,
) -> None:
    RelationshipValidator().validate(
        OntologyRelationship(
            relationship_id=f"{source_type.value}-{relationship_type.value}-{target_type.value}",
            relationship_type=relationship_type,
            source_entity_id="source-1",
            source_entity_type=source_type,
            target_entity_id="target-1",
            target_entity_type=target_type,
            created_by="synchronizer",
        )
    )


def test_validator_rejects_unsupported_generated_from_pair() -> None:
    relationship = OntologyRelationship(
        relationship_id="invalid-job-self-evidence",
        relationship_type=RelationshipType.GENERATED_FROM,
        source_entity_id="job-1",
        source_entity_type=EntityType.JOB,
        target_entity_id="job-2",
        target_entity_type=EntityType.JOB,
        created_by="synchronizer",
    )

    with pytest.raises(InvalidOntologyRelationshipError):
        RelationshipValidator().validate(relationship)


def test_validator_rejects_invalid_relationship_direction() -> None:
    relationship = OntologyRelationship(
        relationship_id="rel-1",
        relationship_type=RelationshipType.HAS_VERSION,
        source_entity_id="candidate-1",
        source_entity_type=EntityType.CANDIDATE,
        target_entity_id="prompt-v1",
        target_entity_type=EntityType.PROMPT_VERSION,
        created_by="tester",
    )

    with pytest.raises(InvalidOntologyRelationshipError):
        RelationshipValidator().validate(relationship)


def test_validator_rejects_reverse_relationship_direction() -> None:
    relationship = OntologyRelationship(
        relationship_id="rel-1",
        relationship_type=RelationshipType.USES,
        source_entity_id="prompt-v1",
        source_entity_type=EntityType.PROMPT_VERSION,
        target_entity_id="candidate-1",
        target_entity_type=EntityType.CANDIDATE,
        created_by="tester",
    )

    with pytest.raises(InvalidOntologyRelationshipError):
        RelationshipValidator().validate(relationship)


def test_validator_rejects_self_relationship_unless_allowed() -> None:
    relationship = OntologyRelationship(
        relationship_id="rel-1",
        relationship_type=RelationshipType.COMPARED_WITH,
        source_entity_id="eval-1",
        source_entity_type=EntityType.EVALUATION_RESULT,
        target_entity_id="eval-1",
        target_entity_type=EntityType.EVALUATION_RESULT,
        created_by="tester",
    )

    with pytest.raises(InvalidOntologyRelationshipError):
        RelationshipValidator().validate(relationship)
