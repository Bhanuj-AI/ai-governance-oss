from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kavach.decisions.enums import DecisionTargetType
from kavach.decisions.exceptions import DecisionValidationError
from kavach.decisions.policies import GovernancePolicy, PolicyRule
from kavach.decisions.policy_enums import (
    PolicyCategory,
    PolicyStatus,
)
from kavach.decisions.validation import (
    coerce_enum,
    copy_mapping,
    require_non_empty,
    require_timezone_aware,
)


@dataclass(frozen=True)
class PolicyDefinition:
    """
    Stable Studio-owned identity for a governed policy.
    """

    policy_id: str
    organization_id: str
    project_id: str
    name: str
    description: str | None
    category: PolicyCategory | str
    owner: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("policy_id", self.policy_id)
        require_non_empty("policy organization_id", self.organization_id)
        require_non_empty("policy project_id", self.project_id)
        require_non_empty("policy name", self.name)
        require_non_empty("policy owner", self.owner)
        require_non_empty("policy created_by", self.created_by)
        require_timezone_aware("policy created_at", self.created_at)
        require_timezone_aware("policy updated_at", self.updated_at)
        object.__setattr__(
            self,
            "category",
            coerce_enum("policy category", PolicyCategory, self.category),
        )
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class PolicyVersion:
    """
    Immutable executable policy content once it leaves DRAFT state.
    """

    policy_id: str
    version: str
    status: PolicyStatus | str
    target_types: Sequence[DecisionTargetType | str]
    rules: Sequence[PolicyRule]
    created_by: str
    created_at: datetime
    activated_at: datetime | None = None
    deprecated_at: datetime | None = None
    archived_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("policy version policy_id", self.policy_id)
        require_non_empty("policy version", self.version)
        require_non_empty("policy version created_by", self.created_by)
        require_timezone_aware("policy version created_at", self.created_at)
        _require_optional_timezone("policy activated_at", self.activated_at)
        _require_optional_timezone("policy deprecated_at", self.deprecated_at)
        _require_optional_timezone("policy archived_at", self.archived_at)

        target_types = tuple(
            coerce_enum("policy target_type", DecisionTargetType, target_type)
            for target_type in self.target_types
        )
        if not target_types:
            raise DecisionValidationError(
                "Decision policy target_types must not be empty."
            )

        rules = tuple(self.rules)
        if not rules:
            raise DecisionValidationError(
                "Decision policy rules must not be empty."
            )

        rule_ids = [rule.rule_id for rule in rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise DecisionValidationError(
                "Decision policy rule IDs must be unique within a version."
            )

        for rule in rules:
            if not isinstance(rule, PolicyRule):
                raise DecisionValidationError(
                    "Decision policy version rules must be PolicyRule "
                    "instances."
                )

        object.__setattr__(
            self,
            "status",
            coerce_enum("policy status", PolicyStatus, self.status),
        )
        object.__setattr__(self, "target_types", target_types)
        object.__setattr__(self, "rules", rules)
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))

    def to_governance_policy(
        self,
        definition: PolicyDefinition,
    ) -> GovernancePolicy:
        return GovernancePolicy(
            policy_id=self.policy_id,
            version=self.version,
            name=definition.name,
            description=definition.description,
            status=self.status,
            target_types=self.target_types,
            rules=self.rules,
            created_by=self.created_by,
            created_at=self.created_at,
            metadata={
                **definition.metadata,
                **self.metadata,
                "category": definition.category.value,
                "owner": definition.owner,
                "project_id": definition.project_id,
                "organization_id": definition.organization_id,
            },
        )


def _require_optional_timezone(
    field_name: str,
    value: datetime | None,
) -> None:
    if value is not None:
        require_timezone_aware(field_name, value)
