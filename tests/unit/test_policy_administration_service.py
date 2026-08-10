from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_governance.decisions import (
    DecisionTargetType,
    PolicyConditionOperator,
    PolicyEffect,
    PolicyStatus,
)
from ai_governance.repositories import InMemoryPolicyAdministrationRepository
from ai_governance.services.policies import (
    InvalidPolicyRequestError,
    PolicyActivationFailedError,
    PolicyAdministrationService,
    PolicyConflictError,
    build_policy_rule,
)


def _service() -> PolicyAdministrationService:
    current = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)

    def clock() -> datetime:
        nonlocal current
        current = current + timedelta(minutes=1)
        return current

    return PolicyAdministrationService(
        InMemoryPolicyAdministrationRepository(),
        id_generator=lambda: "policy-1",
        clock=clock,
    )


def _rule(
    rule_id: str = "rule-1",
    expected_value: object = 0.8,
    effect: str = PolicyEffect.APPROVE.value,
):
    return build_policy_rule(
        rule_id=rule_id,
        name="Groundedness gate",
        conditions=(
            {
                "field_path": "metrics.groundedness.score",
                "operator": PolicyConditionOperator.GREATER_THAN.value,
                "expected_value": expected_value,
            },
        ),
        effect=effect,
        reason_template="Groundedness passed.",
        priority=10,
        severity="HIGH",
        metadata={"source": "unit-test"},
    )


def _create(service: PolicyAdministrationService):
    return service.create_policy(
        name="Release gate",
        description="Approve candidates above groundedness threshold.",
        organization_id="org-1",
        project_id="project-1",
        category="MODEL_RISK",
        owner="risk",
        created_by="admin",
        target_types=(DecisionTargetType.CANDIDATE.value,),
        rules=(_rule(),),
        metadata={"team": "studio"},
    )


def test_create_policy_creates_definition_and_initial_draft() -> None:
    detail = _create(_service())

    assert detail.policy_id == "policy-1"
    assert detail.draft_version is not None
    assert detail.draft_version.version == "1"
    assert detail.draft_version.status == PolicyStatus.DRAFT
    assert detail.active_version is None
    assert detail.metadata == {"team": "studio"}


def test_activate_draft_and_reject_active_update() -> None:
    service = _service()
    _create(service)

    detail = service.activate_version(
        policy_id="policy-1",
        version="1",
        activated_by="admin",
    )

    assert detail.active_version is not None
    assert detail.active_version.version == "1"
    assert detail.draft_version is None

    with pytest.raises(InvalidPolicyRequestError):
        service.update_draft_version(
            policy_id="policy-1",
            version="1",
            target_types=(DecisionTargetType.CANDIDATE.value,),
            rules=(_rule(expected_value=0.9),),
            updated_by="admin",
            metadata={},
        )


def test_new_activation_deprecates_existing_active() -> None:
    service = _service()
    _create(service)
    service.activate_version(
        policy_id="policy-1",
        version="1",
        activated_by="admin",
    )
    service.create_policy_version(
        policy_id="policy-1",
        base_version="1",
        target_types=(DecisionTargetType.CANDIDATE.value,),
        rules=(_rule(expected_value=0.9),),
        created_by="admin",
        metadata={},
    )

    detail = service.activate_version(
        policy_id="policy-1",
        version="2",
        activated_by="admin",
    )

    statuses = {version.version: version.status for version in detail.versions}
    assert statuses == {"1": "DEPRECATED", "2": "ACTIVE"}
    assert detail.active_version is not None
    assert detail.active_version.version == "2"


def test_archived_version_cannot_be_activated() -> None:
    service = _service()
    _create(service)
    service.archive_version(
        policy_id="policy-1",
        version="1",
        archived_by="admin",
    )

    with pytest.raises(PolicyActivationFailedError):
        service.activate_version(
            policy_id="policy-1",
            version="1",
            activated_by="admin",
        )


def test_duplicate_policy_name_in_project_conflicts() -> None:
    service = PolicyAdministrationService(
        InMemoryPolicyAdministrationRepository(),
        id_generator=iter(("policy-1", "policy-2")).__next__,
        clock=lambda: datetime(2026, 7, 4, 12, 0, tzinfo=UTC),
    )
    _create(service)

    with pytest.raises(PolicyConflictError):
        _create(service)


def test_list_policies_filters_and_paginates_latest_created() -> None:
    service = PolicyAdministrationService(
        InMemoryPolicyAdministrationRepository(),
        id_generator=(f"policy-{index}" for index in range(12)).__next__,
        clock=iter(
            datetime(2026, 7, 4, 12, index, tzinfo=UTC)
            for index in range(12)
        ).__next__,
    )
    for index in range(12):
        service.create_policy(
            name=f"Release gate {index:02d}",
            description=f"Policy {index:02d}",
            organization_id="org-1",
            project_id="project-a" if index % 2 == 0 else "project-b",
            category="MODEL_RISK",
            owner="risk" if index % 2 == 0 else "platform",
            created_by="admin",
            target_types=(DecisionTargetType.CANDIDATE.value,),
            rules=(
                _rule(
                    rule_id=f"rule-{index}",
                    effect=(
                        PolicyEffect.APPROVE.value
                        if index % 2 == 0
                        else PolicyEffect.REJECT.value
                    ),
                ),
            ),
            metadata={},
        )

    first_page = service.list_policies(limit=10)
    second_page = service.list_policies(limit=10, offset=10)
    filtered = service.list_policies(
        search="release gate 03",
        project_id="project-b",
        owner="platform",
        effect=PolicyEffect.REJECT.value,
        limit=10,
    )

    assert [item.policy_id for item in first_page][:2] == [
        "policy-11",
        "policy-10",
    ]
    assert len(first_page) == 10
    assert [item.policy_id for item in second_page] == ["policy-1", "policy-0"]
    assert [item.policy_id for item in filtered] == ["policy-3"]


def test_simulate_policy_version_uses_evaluator_trace() -> None:
    service = _service()
    _create(service)

    result = service.simulate_version(
        policy_id="policy-1",
        version="1",
        target_type=DecisionTargetType.CANDIDATE.value,
        target_id="candidate-1",
        evidence={"metrics": {"groundedness": {"score": 0.91}}},
        metadata={"request_id": "sim-1"},
    )

    assert result.matched
    assert result.effect == PolicyEffect.APPROVE.value
    assert result.matched_conditions[0].field_path == (
        "metrics.groundedness.score"
    )
    assert result.evaluation_trace[0].actual_value == 0.91
