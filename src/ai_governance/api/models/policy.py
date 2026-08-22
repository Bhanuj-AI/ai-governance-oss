from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ai_governance.decisions import PolicyCondition, PolicyRule
from ai_governance.decisions.policies import PolicyEvaluationTraceItem
from ai_governance.decisions.policy_administration import PolicyVersion
from ai_governance.services.policies import (
    PolicyDetail,
    PolicyListItem,
    PolicySchema,
    PolicySchemaField,
    PolicySchemaTargetType,
    PolicySimulationResult,
    PolicyVersionSummary,
)


class PolicyConditionRequest(BaseModel):
    field_path: str
    operator: str
    expected_value: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatePolicyRuleRequest(BaseModel):
    rule_id: str
    name: str
    conditions: list[PolicyConditionRequest]
    effect: str
    reason_template: str
    priority: int
    severity: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatePolicyRequest(BaseModel):
    name: str
    description: str | None = None
    organization_id: str
    project_id: str
    category: str
    owner: str
    created_by: str
    target_types: list[str]
    rules: list[CreatePolicyRuleRequest]
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatePolicyVersionRequest(BaseModel):
    base_version: str | None = None
    target_types: list[str]
    rules: list[CreatePolicyRuleRequest]
    created_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateDraftPolicyVersionRequest(BaseModel):
    target_types: list[str]
    rules: list[CreatePolicyRuleRequest]
    updated_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActivatePolicyVersionRequest(BaseModel):
    activated_by: str


class ArchivePolicyVersionRequest(BaseModel):
    archived_by: str


class PolicySimulationRequest(BaseModel):
    target_type: str
    target_id: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyConditionResponse(BaseModel):
    field_path: str
    operator: str
    expected_value: Any | None = None
    metadata: dict[str, Any]

    @classmethod
    def from_domain(
        cls,
        condition: PolicyCondition,
    ) -> PolicyConditionResponse:
        return cls(
            field_path=condition.field_path,
            operator=condition.operator.value,
            expected_value=condition.expected_value,
            metadata=dict(condition.metadata),
        )


class PolicyRuleResponse(BaseModel):
    rule_id: str
    name: str
    priority: int
    effect: str
    reason_template: str
    severity: str | None
    conditions: list[PolicyConditionResponse]
    metadata: dict[str, Any]

    @classmethod
    def from_domain(
        cls,
        rule: PolicyRule,
    ) -> PolicyRuleResponse:
        return cls(
            rule_id=rule.rule_id,
            name=rule.name,
            priority=rule.priority,
            effect=rule.effect.value,
            reason_template=rule.reason_template,
            severity=rule.metadata.get("severity"),
            conditions=[
                PolicyConditionResponse.from_domain(condition)
                for condition in rule.conditions
            ],
            metadata=dict(rule.metadata),
        )


class PolicyVersionResponse(BaseModel):
    policy_id: str
    version: str
    status: str
    target_types: list[str]
    rules: list[PolicyRuleResponse]
    created_by: str
    created_at: datetime
    activated_at: datetime | None
    deprecated_at: datetime | None
    archived_at: datetime | None
    metadata: dict[str, Any]

    @classmethod
    def from_domain(
        cls,
        version: PolicyVersion,
    ) -> PolicyVersionResponse:
        return cls(
            policy_id=version.policy_id,
            version=version.version,
            status=version.status.value,
            target_types=[target_type.value for target_type in version.target_types],
            rules=[PolicyRuleResponse.from_domain(rule) for rule in version.rules],
            created_by=version.created_by,
            created_at=version.created_at,
            activated_at=version.activated_at,
            deprecated_at=version.deprecated_at,
            archived_at=version.archived_at,
            metadata=dict(version.metadata),
        )


class PolicyVersionSummaryResponse(BaseModel):
    policy_id: str
    version: str
    status: str
    target_types: list[str]
    created_by: str
    created_at: datetime
    activated_at: datetime | None
    deprecated_at: datetime | None
    archived_at: datetime | None

    @classmethod
    def from_domain(
        cls,
        version: PolicyVersionSummary,
    ) -> PolicyVersionSummaryResponse:
        return cls(
            policy_id=version.policy_id,
            version=version.version,
            status=version.status,
            target_types=list(version.target_types),
            created_by=version.created_by,
            created_at=version.created_at,
            activated_at=version.activated_at,
            deprecated_at=version.deprecated_at,
            archived_at=version.archived_at,
        )


class PolicyListItemResponse(BaseModel):
    policy_id: str
    name: str
    description: str | None
    organization_id: str
    project_id: str
    category: str
    owner: str
    status: str
    active_version: str | None
    draft_version: str | None
    target_types: list[str]
    highest_priority: int | None
    primary_effect: str | None
    updated_at: datetime
    created_at: datetime

    @classmethod
    def from_domain(
        cls,
        item: PolicyListItem,
    ) -> PolicyListItemResponse:
        return cls(
            policy_id=item.policy_id,
            name=item.name,
            description=item.description,
            organization_id=item.organization_id,
            project_id=item.project_id,
            category=item.category,
            owner=item.owner,
            status=item.status,
            active_version=item.active_version,
            draft_version=item.draft_version,
            target_types=list(item.target_types),
            highest_priority=item.highest_priority,
            primary_effect=item.primary_effect,
            updated_at=item.updated_at,
            created_at=item.created_at,
        )


class PolicyDetailResponse(BaseModel):
    policy_id: str
    name: str
    description: str | None
    organization_id: str
    project_id: str
    category: str
    owner: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    active_version: PolicyVersionResponse | None
    draft_version: PolicyVersionResponse | None
    versions: list[PolicyVersionSummaryResponse]
    metadata: dict[str, Any]

    @classmethod
    def from_domain(
        cls,
        detail: PolicyDetail,
    ) -> PolicyDetailResponse:
        return cls(
            policy_id=detail.policy_id,
            name=detail.name,
            description=detail.description,
            organization_id=detail.organization_id,
            project_id=detail.project_id,
            category=detail.category,
            owner=detail.owner,
            created_by=detail.created_by,
            created_at=detail.created_at,
            updated_at=detail.updated_at,
            active_version=(
                PolicyVersionResponse.from_domain(detail.active_version)
                if detail.active_version is not None
                else None
            ),
            draft_version=(
                PolicyVersionResponse.from_domain(detail.draft_version)
                if detail.draft_version is not None
                else None
            ),
            versions=[
                PolicyVersionSummaryResponse.from_domain(version)
                for version in detail.versions
            ],
            metadata=dict(detail.metadata),
        )


class PolicySchemaFieldResponse(BaseModel):
    field_path: str
    label: str
    value_type: str
    supported_operators: list[str]
    allowed_values: list[Any] | None
    description: str | None

    @classmethod
    def from_domain(
        cls,
        field: PolicySchemaField,
    ) -> PolicySchemaFieldResponse:
        return cls(
            field_path=field.field_path,
            label=field.label,
            value_type=field.value_type,
            supported_operators=list(field.supported_operators),
            allowed_values=(
                list(field.allowed_values) if field.allowed_values is not None else None
            ),
            description=field.description,
        )


class PolicySchemaTargetTypeResponse(BaseModel):
    value: str
    label: str
    description: str | None
    fields: list[PolicySchemaFieldResponse]

    @classmethod
    def from_domain(
        cls,
        target_type: PolicySchemaTargetType,
    ) -> PolicySchemaTargetTypeResponse:
        return cls(
            value=target_type.value,
            label=target_type.label,
            description=target_type.description,
            fields=[
                PolicySchemaFieldResponse.from_domain(field)
                for field in target_type.fields
            ],
        )


class PolicySchemaResponse(BaseModel):
    target_types: list[PolicySchemaTargetTypeResponse]
    operators: list[str]
    effects: list[str]
    statuses: list[str]
    categories: list[str]
    severities: list[str]

    @classmethod
    def from_domain(
        cls,
        schema: PolicySchema,
    ) -> PolicySchemaResponse:
        return cls(
            target_types=[
                PolicySchemaTargetTypeResponse.from_domain(target_type)
                for target_type in schema.target_types
            ],
            operators=list(schema.operators),
            effects=list(schema.effects),
            statuses=list(schema.statuses),
            categories=list(schema.categories),
            severities=list(schema.severities),
        )


class PolicyEvaluationTraceItemResponse(BaseModel):
    rule_id: str
    rule_name: str
    condition_field_path: str
    operator: str
    expected_value: Any | None
    actual_value: Any | None
    matched: bool
    reason: str | None

    @classmethod
    def from_domain(
        cls,
        item: PolicyEvaluationTraceItem,
    ) -> PolicyEvaluationTraceItemResponse:
        return cls(
            rule_id=item.rule_id,
            rule_name=item.rule_name,
            condition_field_path=item.condition_field_path,
            operator=item.operator.value,
            expected_value=item.expected_value,
            actual_value=item.actual_value,
            matched=item.matched,
            reason=item.reason,
        )


class PolicySimulationResponse(BaseModel):
    policy_id: str
    version: str
    target_type: str
    target_id: str
    matched: bool
    matched_rule_id: str | None
    effect: str
    reason: str
    matched_conditions: list[PolicyConditionResponse]
    unmatched_conditions: list[PolicyConditionResponse]
    evaluation_trace: list[PolicyEvaluationTraceItemResponse]
    metadata: dict[str, Any]

    @classmethod
    def from_domain(
        cls,
        result: PolicySimulationResult,
    ) -> PolicySimulationResponse:
        return cls(
            policy_id=result.policy_id,
            version=result.version,
            target_type=result.target_type,
            target_id=result.target_id,
            matched=result.matched,
            matched_rule_id=result.matched_rule_id,
            effect=result.effect,
            reason=result.reason,
            matched_conditions=[
                PolicyConditionResponse.from_domain(condition)
                for condition in result.matched_conditions
            ],
            unmatched_conditions=[
                PolicyConditionResponse.from_domain(condition)
                for condition in result.unmatched_conditions
            ],
            evaluation_trace=[
                PolicyEvaluationTraceItemResponse.from_domain(item)
                for item in result.evaluation_trace
            ],
            metadata=dict(result.metadata),
        )
