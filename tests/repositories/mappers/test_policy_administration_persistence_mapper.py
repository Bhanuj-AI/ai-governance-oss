from datetime import UTC, datetime

from kavach.decisions import (
    DecisionTargetType,
    PolicyCondition,
    PolicyConditionOperator,
    PolicyEffect,
    PolicyRule,
    PolicyStatus,
)
from kavach.decisions.policy_administration import (
    PolicyDefinition,
    PolicyVersion,
)
from kavach.decisions.policy_enums import PolicyCategory
from kavach.repositories.mappers import PolicyAdministrationPersistenceMapper


def test_policy_definition_mapper_round_trips() -> None:
    definition = PolicyDefinition(
        policy_id="policy-1",
        organization_id="org-1",
        project_id="project-1",
        name="Release gate",
        description="Approve high-quality candidates.",
        category=PolicyCategory.MODEL_RISK,
        owner="risk",
        created_by="admin",
        created_at=datetime(2026, 7, 4, 12, tzinfo=UTC),
        updated_at=datetime(2026, 7, 4, 12, 5, tzinfo=UTC),
        metadata={"source": "mapper-test"},
    )

    record = (
        PolicyAdministrationPersistenceMapper.definition_to_persistence_record(
            definition
        )
    )

    assert (
        PolicyAdministrationPersistenceMapper.definition_from_persistence_record(
            record
        )
        == definition
    )


def test_policy_version_mapper_round_trips_rules_and_lifecycle() -> None:
    version = PolicyVersion(
        policy_id="policy-1",
        version="2",
        status=PolicyStatus.ACTIVE,
        target_types=(DecisionTargetType.CANDIDATE,),
        rules=(
            PolicyRule(
                rule_id="quality-gate",
                name="Quality gate",
                conditions=(
                    PolicyCondition(
                        field_path="metrics.groundedness.score",
                        operator=PolicyConditionOperator.GREATER_THAN,
                        expected_value=0.9,
                        metadata={"unit": "score"},
                    ),
                ),
                effect=PolicyEffect.APPROVE,
                reason_template="Quality threshold matched.",
                priority=10,
                metadata={"severity": "HIGH"},
            ),
        ),
        created_by="admin",
        created_at=datetime(2026, 7, 4, 12, tzinfo=UTC),
        activated_at=datetime(2026, 7, 4, 12, 1, tzinfo=UTC),
        metadata={"source": "mapper-test"},
    )

    record = PolicyAdministrationPersistenceMapper.version_to_persistence_record(
        version
    )

    assert (
        PolicyAdministrationPersistenceMapper.version_from_persistence_record(
            record
        )
        == version
    )
