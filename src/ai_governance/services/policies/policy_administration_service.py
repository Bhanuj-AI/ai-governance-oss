from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ai_governance.decisions import (
    DecisionTargetType,
    GovernancePolicy,
    GovernancePolicyEvaluator,
    PolicyCondition,
    PolicyEffect,
    PolicyEvaluationContext,
    PolicyRule,
    PolicyStatus,
)
from ai_governance.decisions.policy_administration import (
    PolicyDefinition,
    PolicyVersion,
)
from ai_governance.decisions.policy_enums import (
    PolicyCategory,
    PolicyConditionOperator,
    PolicySeverity,
)
from ai_governance.ontology import EntityType
from ai_governance.ontology.synchronization import OntologySyncEventPublisherProtocol
from ai_governance.repositories.policy_administration_repository import (
    PolicyAdministrationConflictError,
    PolicyAdministrationRepository,
)


class PolicyAdminNotFoundError(Exception):
    """
    Raised when a policy definition is unknown.
    """


class PolicyVersionNotFoundError(Exception):
    """
    Raised when a policy version is unknown.
    """


class PolicyConflictError(Exception):
    """
    Raised when a policy request conflicts with stored state.
    """


class InvalidPolicyRequestError(Exception):
    """
    Raised when policy admin input is invalid.
    """


class PolicyValidationFailedError(Exception):
    """
    Raised when policy content does not pass backend validation.
    """


class PolicyActivationFailedError(Exception):
    """
    Raised when a policy version cannot be activated.
    """


class PolicyArchiveFailedError(Exception):
    """
    Raised when a policy version cannot be archived.
    """


class PolicySimulationFailedError(Exception):
    """
    Raised when a policy version cannot be simulated.
    """


class PolicySchemaUnavailableError(Exception):
    """
    Raised when backend policy schema metadata cannot be produced.
    """


@dataclass(frozen=True)
class PolicyListItem:
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
    target_types: tuple[str, ...]
    highest_priority: int | None
    primary_effect: str | None
    updated_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class PolicyVersionSummary:
    policy_id: str
    version: str
    status: str
    target_types: tuple[str, ...]
    created_by: str
    created_at: datetime
    activated_at: datetime | None
    deprecated_at: datetime | None
    archived_at: datetime | None


@dataclass(frozen=True)
class PolicyDetail:
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
    active_version: PolicyVersion | None
    draft_version: PolicyVersion | None
    versions: tuple[PolicyVersionSummary, ...]
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class PolicySchemaField:
    field_path: str
    label: str
    value_type: str
    supported_operators: tuple[str, ...]
    allowed_values: tuple[Any, ...] | None = None
    description: str | None = None


@dataclass(frozen=True)
class PolicySchemaTargetType:
    value: str
    label: str
    description: str | None
    fields: tuple[PolicySchemaField, ...]


@dataclass(frozen=True)
class PolicySchema:
    target_types: tuple[PolicySchemaTargetType, ...]
    operators: tuple[str, ...]
    effects: tuple[str, ...]
    statuses: tuple[str, ...]
    categories: tuple[str, ...]
    severities: tuple[str, ...]


@dataclass(frozen=True)
class PolicySimulationResult:
    policy_id: str
    version: str
    target_type: str
    target_id: str
    matched: bool
    matched_rule_id: str | None
    effect: str
    reason: str
    matched_conditions: tuple[PolicyCondition, ...]
    unmatched_conditions: tuple[PolicyCondition, ...]
    evaluation_trace: tuple[Any, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


class PolicyAdministrationService:
    """
    Studio policy administration facade.
    """

    def __init__(
        self,
        repository: PolicyAdministrationRepository,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol | None = None,
    ) -> None:
        self._repository = repository
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._evaluator = GovernancePolicyEvaluator()
        self._ontology_event_publisher = ontology_event_publisher

    def get_policy_schema(self) -> PolicySchema:
        return _policy_schema()

    def create_policy(
        self,
        *,
        name: str,
        description: str | None,
        organization_id: str,
        project_id: str,
        category: str,
        owner: str,
        created_by: str,
        target_types: Sequence[str],
        rules: Sequence[PolicyRule],
        metadata: Mapping[str, Any],
    ) -> PolicyDetail:
        now = self._clock()
        policy_id = self._id_generator()
        definition = PolicyDefinition(
            policy_id=policy_id,
            organization_id=organization_id,
            project_id=project_id,
            name=name,
            description=description,
            category=category,
            owner=owner,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            metadata=metadata,
        )
        version = PolicyVersion(
            policy_id=policy_id,
            version="1",
            status=PolicyStatus.DRAFT,
            target_types=target_types,
            rules=rules,
            created_by=created_by,
            created_at=now,
        )
        self._validate_version(version)

        try:
            self._repository.save_definition(definition)
            self._repository.save_version(version)
        except PolicyAdministrationConflictError as exc:
            raise PolicyConflictError(str(exc)) from exc

        detail = self.get_policy_detail(policy_id)
        self._publish_policy_event("PolicyCreated", definition)
        return detail

    def create_policy_version(
        self,
        *,
        policy_id: str,
        base_version: str | None,
        target_types: Sequence[str],
        rules: Sequence[PolicyRule],
        created_by: str,
        metadata: Mapping[str, Any],
    ) -> PolicyDetail:
        definition = self._get_definition(policy_id)
        if base_version is not None:
            self._get_version(policy_id, base_version)

        version = PolicyVersion(
            policy_id=policy_id,
            version=self._next_version(policy_id),
            status=PolicyStatus.DRAFT,
            target_types=target_types,
            rules=rules,
            created_by=created_by,
            created_at=self._clock(),
            metadata=metadata,
        )
        self._validate_version(version)
        self._repository.save_version(version)
        self._touch_definition(definition)
        detail = self.get_policy_detail(policy_id)
        self._publish_policy_event("PolicyVersionCreated", definition)
        return detail

    def update_draft_version(
        self,
        *,
        policy_id: str,
        version: str,
        target_types: Sequence[str],
        rules: Sequence[PolicyRule],
        updated_by: str,
        metadata: Mapping[str, Any],
    ) -> PolicyDetail:
        existing = self._get_version(policy_id, version)
        if existing.status != PolicyStatus.DRAFT:
            raise InvalidPolicyRequestError(
                "Only draft policy versions can be updated."
            )

        updated = replace(
            existing,
            target_types=tuple(target_types),
            rules=tuple(rules),
            metadata={**existing.metadata, **dict(metadata), "updated_by": updated_by},
        )
        self._validate_version(updated)
        self._repository.save_version(updated)
        definition = self._get_definition(policy_id)
        self._touch_definition(definition)
        detail = self.get_policy_detail(policy_id)
        self._publish_policy_event("PolicyVersionUpdated", definition)
        return detail

    def activate_version(
        self,
        *,
        policy_id: str,
        version: str,
        activated_by: str,
    ) -> PolicyDetail:
        selected = self._get_version(policy_id, version)
        if selected.status == PolicyStatus.ARCHIVED:
            raise PolicyActivationFailedError(
                "Archived policy versions cannot be activated."
            )
        if selected.status != PolicyStatus.DRAFT:
            raise PolicyActivationFailedError(
                "Only draft policy versions can be activated."
            )

        now = self._clock()
        active = self._repository.get_active_version(policy_id)
        if active is not None:
            self._repository.save_version(
                replace(
                    active,
                    status=PolicyStatus.DEPRECATED,
                    deprecated_at=now,
                )
            )

        self._repository.save_version(
            replace(
                selected,
                status=PolicyStatus.ACTIVE,
                activated_at=now,
                metadata={
                    **selected.metadata,
                    "activated_by": activated_by,
                },
            )
        )
        definition = self._get_definition(policy_id)
        self._touch_definition(definition)
        detail = self.get_policy_detail(policy_id)
        self._publish_policy_event("PolicyVersionActivated", definition)
        return detail

    def archive_version(
        self,
        *,
        policy_id: str,
        version: str,
        archived_by: str,
    ) -> PolicyDetail:
        selected = self._get_version(policy_id, version)
        if selected.status == PolicyStatus.ARCHIVED:
            return self.get_policy_detail(policy_id)

        self._repository.save_version(
            replace(
                selected,
                status=PolicyStatus.ARCHIVED,
                archived_at=self._clock(),
                metadata={
                    **selected.metadata,
                    "archived_by": archived_by,
                },
            )
        )
        definition = self._get_definition(policy_id)
        self._touch_definition(definition)
        detail = self.get_policy_detail(policy_id)
        self._publish_policy_event("PolicyVersionArchived", definition)
        return detail

    def _publish_policy_event(
        self,
        event_type: str,
        definition: PolicyDefinition,
    ) -> None:
        if self._ontology_event_publisher is None:
            return
        active_version = self._repository.get_active_version(definition.policy_id)
        self._ontology_event_publisher.publish_entity_event(
            event_type,
            entity_type=EntityType.POLICY.value,
            entity_id=definition.policy_id,
            scope_identifier="policy_administration",
            payload={
                "policy_id": definition.policy_id,
                "name": definition.name,
                "status": (
                    active_version.status.value
                    if active_version is not None
                    else "DRAFT"
                ),
                "active_version": (
                    active_version.version if active_version is not None else None
                ),
            },
            organization_id=definition.organization_id,
            project_id=definition.project_id,
        )

    def list_policies(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        search: str | None = None,
        owner: str | None = None,
        category: str | None = None,
        status: str | None = None,
        target_type: str | None = None,
        effect: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PolicyListItem]:
        definitions = self._repository.list_definitions(
            organization_id=organization_id,
            project_id=project_id,
            search=search,
            owner=owner,
            category=category,
            status=status,
            target_type=target_type,
            effect=effect,
            limit=limit,
            offset=offset,
        )
        return [self._list_item(definition) for definition in definitions]

    def get_policy_detail(
        self,
        policy_id: str,
    ) -> PolicyDetail:
        definition = self._get_definition(policy_id)
        versions = self._repository.list_versions(policy_id)
        active = next(
            (
                version
                for version in versions
                if version.status == PolicyStatus.ACTIVE
            ),
            None,
        )
        draft = next(
            (
                version
                for version in reversed(versions)
                if version.status == PolicyStatus.DRAFT
            ),
            None,
        )
        return PolicyDetail(
            policy_id=definition.policy_id,
            name=definition.name,
            description=definition.description,
            organization_id=definition.organization_id,
            project_id=definition.project_id,
            category=definition.category.value,
            owner=definition.owner,
            created_by=definition.created_by,
            created_at=definition.created_at,
            updated_at=definition.updated_at,
            active_version=active,
            draft_version=draft,
            versions=tuple(self._version_summary(version) for version in versions),
            metadata=definition.metadata,
        )

    def get_policy_version(
        self,
        policy_id: str,
        version: str,
    ) -> PolicyVersion:
        self._get_definition(policy_id)
        return self._get_version(policy_id, version)

    def simulate_version(
        self,
        *,
        policy_id: str,
        version: str,
        target_type: str,
        target_id: str,
        evidence: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> PolicySimulationResult:
        definition = self._get_definition(policy_id)
        policy_version = self._get_version(policy_id, version)
        governance_policy = policy_version.to_governance_policy(definition)
        trace_outcome = self._evaluator.evaluate_with_trace(
            governance_policy,
            PolicyEvaluationContext(
                target_type=target_type,
                target_id=target_id,
                evidence=evidence,
                metadata=metadata,
            ),
        )

        outcome = trace_outcome.outcome
        return PolicySimulationResult(
            policy_id=policy_id,
            version=version,
            target_type=target_type,
            target_id=target_id,
            matched=outcome.matched,
            matched_rule_id=outcome.matched_rule_id,
            effect=outcome.effect.value,
            reason=outcome.reason,
            matched_conditions=tuple(trace_outcome.matched_conditions),
            unmatched_conditions=tuple(trace_outcome.unmatched_conditions),
            evaluation_trace=tuple(trace_outcome.evaluation_trace),
            metadata={**metadata, **outcome.metadata},
        )

    def materialize_governance_policy(
        self,
        policy_id: str,
        version: str,
    ) -> GovernancePolicy:
        definition = self._get_definition(policy_id)
        policy_version = self._get_version(policy_id, version)
        return policy_version.to_governance_policy(definition)

    def _get_definition(
        self,
        policy_id: str,
    ) -> PolicyDefinition:
        definition = self._repository.get_definition(policy_id)
        if definition is None:
            raise PolicyAdminNotFoundError(
                f"Policy '{policy_id}' does not exist."
            )
        return definition

    def _get_version(
        self,
        policy_id: str,
        version: str,
    ) -> PolicyVersion:
        policy_version = self._repository.get_version(policy_id, version)
        if policy_version is None:
            raise PolicyVersionNotFoundError(
                f"Policy '{policy_id}' version '{version}' does not exist."
            )
        return policy_version

    def _next_version(
        self,
        policy_id: str,
    ) -> str:
        numeric_versions = []
        for version in self._repository.list_versions(policy_id):
            try:
                numeric_versions.append(int(version.version))
            except ValueError:
                continue
        return str((max(numeric_versions) if numeric_versions else 0) + 1)

    def _touch_definition(
        self,
        definition: PolicyDefinition,
    ) -> None:
        self._repository.save_definition(
            replace(definition, updated_at=self._clock())
        )

    def _list_item(
        self,
        definition: PolicyDefinition,
    ) -> PolicyListItem:
        versions = self._repository.list_versions(definition.policy_id)
        active = next(
            (
                version
                for version in versions
                if version.status == PolicyStatus.ACTIVE
            ),
            None,
        )
        draft = next(
            (
                version
                for version in reversed(versions)
                if version.status == PolicyStatus.DRAFT
            ),
            None,
        )
        visible = active or draft or (versions[-1] if versions else None)
        rules = visible.rules if visible is not None else ()
        target_types = visible.target_types if visible is not None else ()
        highest_priority = min((rule.priority for rule in rules), default=None)
        primary_effect = rules[0].effect.value if rules else None
        status = visible.status.value if visible is not None else PolicyStatus.DRAFT.value

        return PolicyListItem(
            policy_id=definition.policy_id,
            name=definition.name,
            description=definition.description,
            organization_id=definition.organization_id,
            project_id=definition.project_id,
            category=definition.category.value,
            owner=definition.owner,
            status=status,
            active_version=active.version if active is not None else None,
            draft_version=draft.version if draft is not None else None,
            target_types=tuple(target_type.value for target_type in target_types),
            highest_priority=highest_priority,
            primary_effect=primary_effect,
            updated_at=definition.updated_at,
            created_at=definition.created_at,
        )

    def _version_summary(
        self,
        version: PolicyVersion,
    ) -> PolicyVersionSummary:
        return PolicyVersionSummary(
            policy_id=version.policy_id,
            version=version.version,
            status=version.status.value,
            target_types=tuple(
                target_type.value for target_type in version.target_types
            ),
            created_by=version.created_by,
            created_at=version.created_at,
            activated_at=version.activated_at,
            deprecated_at=version.deprecated_at,
            archived_at=version.archived_at,
        )

    def _validate_version(
        self,
        version: PolicyVersion,
    ) -> None:
        field_map = {
            field.field_path: field
            for target_type in _policy_schema().target_types
            for field in target_type.fields
        }
        for rule in version.rules:
            for condition in rule.conditions:
                schema_field = field_map.get(condition.field_path)
                if (
                    schema_field is not None
                    and condition.operator.value
                    not in schema_field.supported_operators
                ):
                    raise PolicyValidationFailedError(
                        "Operator is not supported for policy field "
                        f"'{condition.field_path}'."
                    )


def build_policy_rule(
    *,
    rule_id: str,
    name: str,
    conditions: Sequence[Mapping[str, Any]],
    effect: str,
    reason_template: str,
    priority: int,
    severity: str | None,
    metadata: Mapping[str, Any],
) -> PolicyRule:
    rule_metadata = dict(metadata)
    if severity is not None:
        rule_metadata["severity"] = PolicySeverity(severity).value
    return PolicyRule(
        rule_id=rule_id,
        name=name,
        conditions=tuple(
            PolicyCondition(
                field_path=str(condition["field_path"]),
                operator=str(condition["operator"]),
                expected_value=condition.get("expected_value"),
                metadata=condition.get("metadata", {}),
            )
            for condition in conditions
        ),
        effect=effect,
        reason_template=reason_template,
        priority=priority,
        metadata=rule_metadata,
    )


def _policy_schema() -> PolicySchema:
    comparison = (
        PolicyConditionOperator.GREATER_THAN.value,
        PolicyConditionOperator.GREATER_THAN_OR_EQUAL.value,
        PolicyConditionOperator.LESS_THAN.value,
        PolicyConditionOperator.LESS_THAN_OR_EQUAL.value,
        PolicyConditionOperator.EQUALS.value,
        PolicyConditionOperator.NOT_EQUALS.value,
        PolicyConditionOperator.EXISTS.value,
        PolicyConditionOperator.MISSING.value,
    )
    string_ops = (
        PolicyConditionOperator.EQUALS.value,
        PolicyConditionOperator.NOT_EQUALS.value,
        PolicyConditionOperator.IN.value,
        PolicyConditionOperator.NOT_IN.value,
        PolicyConditionOperator.EXISTS.value,
        PolicyConditionOperator.MISSING.value,
    )
    return PolicySchema(
        target_types=(
            PolicySchemaTargetType(
                value=DecisionTargetType.CANDIDATE.value,
                label="Candidate",
                description="Experiment candidate evidence.",
                fields=(
                    PolicySchemaField(
                        field_path="metrics.groundedness.score",
                        label="Groundedness score",
                        value_type="number",
                        supported_operators=comparison,
                    ),
                    PolicySchemaField(
                        field_path="metrics.answer_relevance.score",
                        label="Answer relevance score",
                        value_type="number",
                        supported_operators=comparison,
                    ),
                    PolicySchemaField(
                        field_path="cost.estimated_usd",
                        label="Estimated cost",
                        value_type="number",
                        supported_operators=comparison,
                    ),
                    PolicySchemaField(
                        field_path="drift.severity",
                        label="Drift severity",
                        value_type="string",
                        supported_operators=string_ops,
                        allowed_values=("LOW", "MEDIUM", "HIGH", "CRITICAL"),
                    ),
                ),
            ),
            PolicySchemaTargetType(
                value=DecisionTargetType.PROMPT_VERSION.value,
                label="Prompt version",
                description="Prompt registry version evidence.",
                fields=(
                    PolicySchemaField(
                        field_path="prompt.status",
                        label="Prompt status",
                        value_type="string",
                        supported_operators=string_ops,
                    ),
                    PolicySchemaField(
                        field_path="prompt.variables.count",
                        label="Prompt variable count",
                        value_type="number",
                        supported_operators=comparison,
                    ),
                ),
            ),
            PolicySchemaTargetType(
                value=DecisionTargetType.MODEL_VERSION.value,
                label="Model version",
                description="Model registry version evidence.",
                fields=(
                    PolicySchemaField(
                        field_path="model.provider",
                        label="Provider",
                        value_type="string",
                        supported_operators=string_ops,
                    ),
                    PolicySchemaField(
                        field_path="model.risk_tier",
                        label="Risk tier",
                        value_type="string",
                        supported_operators=string_ops,
                    ),
                ),
            ),
        ),
        operators=tuple(operator.value for operator in PolicyConditionOperator),
        effects=tuple(effect.value for effect in PolicyEffect),
        statuses=tuple(status.value for status in PolicyStatus),
        categories=tuple(category.value for category in PolicyCategory),
        severities=tuple(severity.value for severity in PolicySeverity),
    )
