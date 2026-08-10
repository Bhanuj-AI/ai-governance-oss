from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ai_governance.decisions import (
    DecisionTargetType,
    PolicyCondition,
    PolicyConditionOperator,
    PolicyEffect,
    PolicyRule,
    PolicyStatus,
)
from ai_governance.decisions.policy_administration import (
    PolicyDefinition,
    PolicyVersion,
)
from ai_governance.decisions.policy_enums import PolicyCategory
from ai_governance.repositories.policy_administration_repository import (
    PolicyAdministrationConflictError,
    PolicyAdministrationRepository,
)


class PolicyAdministrationRepositoryContract(ABC):
    """
    Behavioral contract for Studio policy administration repositories.
    """

    @abstractmethod
    def repository(self) -> PolicyAdministrationRepository:
        """
        Return a fresh repository instance.
        """

    def test_should_save_and_load_policy_definition_and_version(self) -> None:
        repository = self.repository()
        definition = self.create_definition()
        version = self.create_version()

        repository.save_definition(definition)
        repository.save_version(version)

        assert repository.get_definition(definition.policy_id) == definition
        assert repository.get_version(version.policy_id, version.version) == version
        assert repository.list_versions(definition.policy_id) == [version]
        assert repository.get_active_version(definition.policy_id) == version

    def test_should_replace_definition_with_same_id(self) -> None:
        repository = self.repository()
        definition = self.create_definition()
        replacement = replace(
            definition,
            description="Updated policy description.",
            updated_at=definition.updated_at + timedelta(minutes=5),
        )

        repository.save_definition(definition)
        repository.save_definition(replacement)

        assert repository.get_definition(definition.policy_id) == replacement

    def test_should_reject_duplicate_policy_name_in_project(self) -> None:
        repository = self.repository()
        repository.save_definition(self.create_definition())

        with pytest.raises(PolicyAdministrationConflictError):
            repository.save_definition(
                self.create_definition(policy_id="policy-2")
            )

    def test_should_list_filter_and_paginate_definitions(self) -> None:
        repository = self.repository()
        for index in range(12):
            project_id = "project-a" if index % 2 == 0 else "project-b"
            effect = (
                PolicyEffect.APPROVE
                if index % 2 == 0
                else PolicyEffect.REJECT
            )
            definition = self.create_definition(
                policy_id=f"policy-{index}",
                project_id=project_id,
                name=f"Release gate {index:02d}",
                owner="risk" if index % 2 == 0 else "platform",
                created_at=datetime(2026, 7, 4, 12, index, tzinfo=UTC),
            )
            version = self.create_version(
                policy_id=definition.policy_id,
                effect=effect,
            )
            repository.save_definition(definition)
            repository.save_version(version)

        first_page = repository.list_definitions(limit=10)
        second_page = repository.list_definitions(limit=10, offset=10)
        filtered = repository.list_definitions(
            project_id="project-b",
            search="release gate 03",
            owner="platform",
            status=PolicyStatus.ACTIVE,
            target_type=DecisionTargetType.CANDIDATE,
            effect=PolicyEffect.REJECT,
            limit=10,
        )

        assert [item.policy_id for item in first_page][:2] == [
            "policy-11",
            "policy-10",
        ]
        assert len(first_page) == 10
        assert [item.policy_id for item in second_page] == [
            "policy-1",
            "policy-0",
        ]
        assert [item.policy_id for item in filtered] == ["policy-3"]

    def test_should_deprecate_existing_active_version_atomically(self) -> None:
        repository = self.repository()
        definition = self.create_definition()
        first = self.create_version(version="1")
        second = self.create_version(
            version="2",
            created_at=datetime(2026, 7, 4, 13, tzinfo=UTC),
            activated_at=datetime(2026, 7, 4, 13, 5, tzinfo=UTC),
        )

        repository.save_definition(definition)
        repository.save_version(first)
        repository.save_version(second)

        assert repository.get_active_version(definition.policy_id) == second
        old_version = repository.get_version(definition.policy_id, "1")
        assert old_version is not None
        assert old_version.status == PolicyStatus.DEPRECATED
        assert old_version.deprecated_at == second.activated_at

    def test_should_archive_active_version(self) -> None:
        repository = self.repository()
        definition = self.create_definition()
        version = self.create_version()
        archived = replace(
            version,
            status=PolicyStatus.ARCHIVED,
            archived_at=datetime(2026, 7, 4, 14, tzinfo=UTC),
        )

        repository.save_definition(definition)
        repository.save_version(version)
        repository.save_version(archived)

        assert repository.get_active_version(definition.policy_id) is None
        assert repository.get_version(definition.policy_id, "1") == archived

    def create_definition(
        self,
        *,
        policy_id: str = "policy-1",
        project_id: str = "project-a",
        name: str = "Release gate",
        owner: str = "risk",
        created_at: datetime = datetime(2026, 7, 4, 12, tzinfo=UTC),
    ) -> PolicyDefinition:
        return PolicyDefinition(
            policy_id=policy_id,
            organization_id="org-1",
            project_id=project_id,
            name=name,
            description="Approve candidates above quality thresholds.",
            category=PolicyCategory.MODEL_RISK,
            owner=owner,
            created_by="admin",
            created_at=created_at,
            updated_at=created_at,
            metadata={"team": "studio"},
        )

    def create_version(
        self,
        *,
        policy_id: str = "policy-1",
        version: str = "1",
        status: PolicyStatus = PolicyStatus.ACTIVE,
        effect: PolicyEffect = PolicyEffect.APPROVE,
        created_at: datetime = datetime(2026, 7, 4, 12, 1, tzinfo=UTC),
        activated_at: datetime | None = datetime(2026, 7, 4, 12, 2, tzinfo=UTC),
    ) -> PolicyVersion:
        return PolicyVersion(
            policy_id=policy_id,
            version=version,
            status=status,
            target_types=(DecisionTargetType.CANDIDATE,),
            rules=(
                PolicyRule(
                    rule_id="quality-gate",
                    name="Quality gate",
                    conditions=(
                        PolicyCondition(
                            field_path="metrics.groundedness.score",
                            operator=PolicyConditionOperator.GREATER_THAN,
                            expected_value=0.8,
                            metadata={"source": "contract"},
                        ),
                    ),
                    effect=effect,
                    reason_template="Quality threshold matched.",
                    priority=10,
                    metadata={"severity": "HIGH"},
                ),
            ),
            created_by="admin",
            created_at=created_at,
            activated_at=activated_at,
            metadata={"source": "contract"},
        )
