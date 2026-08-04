from __future__ import annotations

from dataclasses import dataclass

from kavach.ontology.enums import Cardinality, EntityType, RelationshipType
from kavach.ontology.exceptions import InvalidOntologyRelationshipError
from kavach.ontology.models import OntologyRelationship


@dataclass(frozen=True)
class RelationshipEndpointRule:
    """
    One allowed source and target pair for an ontology relationship.

    The flags represent the obvious uniqueness constraints that can be safely
    enforced in the foundation layer without implementing a full graph schema
    reasoner. For example, `PRODUCES` is unique per source and target, while
    `GENERATED_FROM` is many-to-many evidence linkage.
    """

    source_type: str
    target_type: str
    unique_per_source: bool = False
    unique_per_target: bool = False
    unique_per_source_target_type: bool = False
    allow_self: bool = False


@dataclass(frozen=True)
class RelationshipRule:
    """
    Validation rule for a directed ontology relationship type.

    Rules are pair-specific rather than broad source/target sets so a
    relationship such as `HAS_VERSION` can allow `Prompt -> PromptVersion`
    without accidentally allowing `Prompt -> ModelVersion`.
    """

    relationship_type: str
    endpoint_rules: tuple[RelationshipEndpointRule, ...]
    cardinality: Cardinality

    @property
    def allowed_sources(self) -> set[str]:
        return {rule.source_type for rule in self.endpoint_rules}

    @property
    def allowed_targets(self) -> set[str]:
        return {rule.target_type for rule in self.endpoint_rules}

    def endpoint_rule(
        self,
        source_type: str,
        target_type: str,
    ) -> RelationshipEndpointRule | None:
        for rule in self.endpoint_rules:
            if rule.source_type == source_type and rule.target_type == target_type:
                return rule
        return None


def _pair(
    source: EntityType,
    target: EntityType,
    *,
    unique_per_source: bool = False,
    unique_per_target: bool = False,
    unique_per_source_target_type: bool = False,
    allow_self: bool = False,
) -> RelationshipEndpointRule:
    return RelationshipEndpointRule(
        source_type=source.value,
        target_type=target.value,
        unique_per_source=unique_per_source,
        unique_per_target=unique_per_target,
        unique_per_source_target_type=unique_per_source_target_type,
        allow_self=allow_self,
    )


VERSIONED_ASSET_PAIRS = (
    _pair(
        EntityType.PROMPT,
        EntityType.PROMPT_VERSION,
        unique_per_target=True,
    ),
    _pair(
        EntityType.MODEL,
        EntityType.MODEL_VERSION,
        unique_per_target=True,
    ),
    _pair(
        EntityType.DATASET,
        EntityType.DATASET_VERSION,
        unique_per_target=True,
    ),
)

VERSION_OF_PAIRS = (
    _pair(
        EntityType.PROMPT_VERSION,
        EntityType.PROMPT,
        unique_per_source=True,
    ),
    _pair(
        EntityType.MODEL_VERSION,
        EntityType.MODEL,
        unique_per_source=True,
    ),
    _pair(
        EntityType.DATASET_VERSION,
        EntityType.DATASET,
        unique_per_source=True,
    ),
)

SUPERSEDES_PAIRS = tuple(
    _pair(entity_type, entity_type, allow_self=False)
    for entity_type in (
        EntityType.PROMPT_VERSION,
        EntityType.MODEL_VERSION,
        EntityType.DATASET_VERSION,
        EntityType.GOVERNANCE_DECISION,
        EntityType.POLICY,
    )
)

OWNED_ENTITY_TYPES = tuple(entity_type for entity_type in EntityType)

CREATED_ENTITY_TYPES = tuple(entity_type for entity_type in EntityType)

# Evidence is deliberately defined per producer.  A broad shared list made it
# easy to accept relationships no synchronizer emits (for example Job -> Job),
# while still rejecting legitimate evidence such as GovernanceDecision -> Metric.
# Keep these sets aligned with the concrete projection adapters below.
JOB_INPUT_EVIDENCE_TYPES = (
    EntityType.EVALUATION_RESULT,
    EntityType.EVALUATION_RUN,
    EntityType.LEADERBOARD,
    EntityType.DRIFT_ANALYSIS,
    EntityType.GOVERNANCE_REPORT,
)

GOVERNANCE_INSIGHT_EVIDENCE_TYPES = (
    EntityType.EVALUATION_RESULT,
    EntityType.EVALUATION_RUN,
    EntityType.JOB,
    EntityType.CANDIDATE,
    EntityType.EXPERIMENT,
    EntityType.MCP_AUDIT_RECORD,
)

GOVERNANCE_DECISION_EVIDENCE_TYPES = (
    EntityType.EVALUATION_RESULT,
    EntityType.METRIC,
    EntityType.DRIFT_ANALYSIS,
    EntityType.LEADERBOARD,
    EntityType.JOB,
    EntityType.MCP_AUDIT_RECORD,
    EntityType.POLICY,
)

DECISION_TARGET_TYPES = (
    EntityType.CANDIDATE,
    EntityType.EXPERIMENT,
    EntityType.PROMPT_VERSION,
    EntityType.MODEL_VERSION,
    EntityType.DATASET_VERSION,
    EntityType.EVALUATION_RUN,
    EntityType.EVALUATION_RESULT,
    EntityType.JOB,
    EntityType.GOVERNANCE_DECISION,
)

RESOURCE_REFERENCE_TYPES = (
    EntityType.PROMPT_VERSION,
    EntityType.MODEL_VERSION,
    EntityType.DATASET_VERSION,
    EntityType.EXPERIMENT,
    EntityType.CANDIDATE,
    EntityType.EVALUATION_RUN,
    EntityType.JOB,
)

RESULT_TYPES = (
    EntityType.EVALUATION_RESULT,
    EntityType.EVALUATION_RUN,
    EntityType.LEADERBOARD,
    EntityType.DRIFT_ANALYSIS,
    EntityType.GOVERNANCE_REPORT,
)

GENERATED_FROM_PAIRS = (
    *(_pair(EntityType.JOB, target) for target in JOB_INPUT_EVIDENCE_TYPES),
    _pair(EntityType.LEADERBOARD, EntityType.EVALUATION_RUN),
    *(
        _pair(EntityType.GOVERNANCE_INSIGHT, target)
        for target in GOVERNANCE_INSIGHT_EVIDENCE_TYPES
    ),
    *(
        _pair(EntityType.GOVERNANCE_DECISION, target)
        for target in GOVERNANCE_DECISION_EVIDENCE_TYPES
    ),
    *(
        _pair(EntityType.GOVERNANCE_REPORT, target)
        for target in GOVERNANCE_INSIGHT_EVIDENCE_TYPES
    ),
    _pair(EntityType.REPLAY, EntityType.EVALUATION_RESULT),
)

RULES: dict[str, RelationshipRule] = {
    RelationshipType.HAS_VERSION.value: RelationshipRule(
        relationship_type=RelationshipType.HAS_VERSION.value,
        endpoint_rules=VERSIONED_ASSET_PAIRS,
        cardinality=Cardinality.ONE_TO_MANY,
    ),
    RelationshipType.VERSION_OF.value: RelationshipRule(
        relationship_type=RelationshipType.VERSION_OF.value,
        endpoint_rules=VERSION_OF_PAIRS,
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.SUPERSEDES.value: RelationshipRule(
        relationship_type=RelationshipType.SUPERSEDES.value,
        endpoint_rules=SUPERSEDES_PAIRS,
        cardinality=Cardinality.ZERO_OR_ONE_TO_ONE,
    ),
    RelationshipType.OWNED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.OWNED_BY.value,
        endpoint_rules=tuple(
            _pair(entity_type, EntityType.ACTOR)
            for entity_type in OWNED_ENTITY_TYPES
            if entity_type != EntityType.ACTOR
        ),
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.CREATED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.CREATED_BY.value,
        endpoint_rules=tuple(
            _pair(entity_type, EntityType.ACTOR)
            for entity_type in CREATED_ENTITY_TYPES
            if entity_type != EntityType.ACTOR
        ),
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.HAS_CANDIDATE.value: RelationshipRule(
        relationship_type=RelationshipType.HAS_CANDIDATE.value,
        endpoint_rules=(
            _pair(
                EntityType.EXPERIMENT,
                EntityType.CANDIDATE,
                unique_per_target=True,
            ),
        ),
        cardinality=Cardinality.ONE_TO_MANY,
    ),
    RelationshipType.PARTICIPATES_IN.value: RelationshipRule(
        relationship_type=RelationshipType.PARTICIPATES_IN.value,
        endpoint_rules=(
            _pair(
                EntityType.CANDIDATE,
                EntityType.EXPERIMENT,
                unique_per_source=True,
            ),
        ),
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.USES.value: RelationshipRule(
        relationship_type=RelationshipType.USES.value,
        endpoint_rules=(
            _pair(
                EntityType.CANDIDATE,
                EntityType.PROMPT_VERSION,
                unique_per_source_target_type=True,
            ),
            _pair(
                EntityType.CANDIDATE,
                EntityType.MODEL_VERSION,
                unique_per_source_target_type=True,
            ),
            _pair(
                EntityType.CANDIDATE,
                EntityType.DATASET_VERSION,
                unique_per_source_target_type=True,
            ),
            _pair(
                EntityType.WORKFLOW_EXECUTION,
                EntityType.PROMPT_VERSION,
                unique_per_source_target_type=True,
            ),
            _pair(
                EntityType.WORKFLOW_EXECUTION,
                EntityType.MODEL_VERSION,
                unique_per_source_target_type=True,
            ),
            _pair(
                EntityType.WORKFLOW_EXECUTION,
                EntityType.DATASET_VERSION,
                unique_per_source_target_type=True,
            ),
        ),
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.EVALUATED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.EVALUATED_BY.value,
        endpoint_rules=(
            _pair(EntityType.CANDIDATE, EntityType.EVALUATION_PROVIDER),
            _pair(EntityType.EVALUATION_RUN, EntityType.EVALUATION_PROVIDER),
            _pair(EntityType.EVALUATION_RESULT, EntityType.EVALUATION_PROVIDER),
        ),
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.HAS_RUN.value: RelationshipRule(
        relationship_type=RelationshipType.HAS_RUN.value,
        endpoint_rules=(
            _pair(
                EntityType.EXPERIMENT,
                EntityType.EVALUATION_RUN,
                unique_per_target=True,
            ),
        ),
        cardinality=Cardinality.ONE_TO_MANY,
    ),
    RelationshipType.EXECUTES.value: RelationshipRule(
        relationship_type=RelationshipType.EXECUTES.value,
        endpoint_rules=(
            _pair(
                EntityType.EVALUATION_RUN,
                EntityType.CANDIDATE,
                unique_per_source=True,
            ),
        ),
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.PRODUCES.value: RelationshipRule(
        relationship_type=RelationshipType.PRODUCES.value,
        endpoint_rules=(
            _pair(
                EntityType.EVALUATION_RUN,
                EntityType.EVALUATION_RESULT,
                unique_per_source=True,
                unique_per_target=True,
            ),
            _pair(EntityType.WORKFLOW_EXECUTION, EntityType.EVALUATION_RESULT),
            _pair(EntityType.REPLAY, EntityType.WORKFLOW_EXECUTION),
            _pair(EntityType.REPLAY, EntityType.EVALUATION_RESULT),
            _pair(EntityType.REPLAY, EntityType.EVALUATION_COMPARISON),
        ),
        cardinality=Cardinality.ZERO_OR_ONE_TO_ONE,
    ),
    RelationshipType.HAS_METRIC.value: RelationshipRule(
        relationship_type=RelationshipType.HAS_METRIC.value,
        endpoint_rules=(_pair(EntityType.EVALUATION_RESULT, EntityType.METRIC),),
        cardinality=Cardinality.ONE_TO_MANY,
    ),
    RelationshipType.HAS_ARTIFACT.value: RelationshipRule(
        relationship_type=RelationshipType.HAS_ARTIFACT.value,
        endpoint_rules=(
            _pair(EntityType.EVALUATION_RESULT, EntityType.EVALUATION_ARTIFACT),
        ),
        cardinality=Cardinality.ZERO_TO_MANY,
    ),
    RelationshipType.RECORDED_IN.value: RelationshipRule(
        relationship_type=RelationshipType.RECORDED_IN.value,
        endpoint_rules=(
            _pair(EntityType.EVALUATION_RESULT, EntityType.EVALUATION_HISTORY),
        ),
        cardinality=Cardinality.MANY_TO_MANY,
    ),
    RelationshipType.COMPARED_WITH.value: RelationshipRule(
        relationship_type=RelationshipType.COMPARED_WITH.value,
        endpoint_rules=(
            _pair(EntityType.EVALUATION_RESULT, EntityType.EVALUATION_RESULT),
        ),
        cardinality=Cardinality.MANY_TO_MANY,
    ),
    RelationshipType.GENERATES.value: RelationshipRule(
        relationship_type=RelationshipType.GENERATES.value,
        endpoint_rules=(_pair(EntityType.EVALUATION_COMPARISON, EntityType.METRIC),),
        cardinality=Cardinality.ONE_TO_MANY,
    ),
    RelationshipType.CAUSED_DRIFT.value: RelationshipRule(
        relationship_type=RelationshipType.CAUSED_DRIFT.value,
        endpoint_rules=(
            _pair(
                EntityType.EVALUATION_COMPARISON,
                EntityType.DRIFT_ANALYSIS,
                unique_per_source=True,
                unique_per_target=True,
            ),
            _pair(EntityType.REPLAY, EntityType.DRIFT_ANALYSIS),
        ),
        cardinality=Cardinality.ZERO_OR_ONE_TO_ONE,
    ),
    RelationshipType.RANKED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.RANKED_BY.value,
        endpoint_rules=(_pair(EntityType.CANDIDATE, EntityType.LEADERBOARD),),
        cardinality=Cardinality.MANY_TO_MANY,
    ),
    RelationshipType.HAS_ENTRY.value: RelationshipRule(
        relationship_type=RelationshipType.HAS_ENTRY.value,
        endpoint_rules=(
            _pair(
                EntityType.LEADERBOARD,
                EntityType.LEADERBOARD_ENTRY,
                unique_per_target=True,
            ),
        ),
        cardinality=Cardinality.ONE_TO_MANY,
    ),
    RelationshipType.RANKS.value: RelationshipRule(
        relationship_type=RelationshipType.RANKS.value,
        endpoint_rules=(
            _pair(
                EntityType.LEADERBOARD_ENTRY,
                EntityType.CANDIDATE,
                unique_per_source=True,
            ),
        ),
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.RECOMMENDS.value: RelationshipRule(
        relationship_type=RelationshipType.RECOMMENDS.value,
        endpoint_rules=(
            _pair(EntityType.LEADERBOARD, EntityType.CANDIDATE),
            _pair(EntityType.GOVERNANCE_INSIGHT, EntityType.CANDIDATE),
        ),
        cardinality=Cardinality.ZERO_OR_ONE_TO_MANY,
    ),
    RelationshipType.GENERATED_FROM.value: RelationshipRule(
        relationship_type=RelationshipType.GENERATED_FROM.value,
        endpoint_rules=GENERATED_FROM_PAIRS,
        cardinality=Cardinality.MANY_TO_MANY,
    ),
    RelationshipType.DECIDES_ON.value: RelationshipRule(
        relationship_type=RelationshipType.DECIDES_ON.value,
        endpoint_rules=tuple(
            _pair(EntityType.GOVERNANCE_DECISION, target)
            for target in DECISION_TARGET_TYPES
        ),
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.APPROVED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.APPROVED_BY.value,
        endpoint_rules=(_pair(EntityType.GOVERNANCE_DECISION, EntityType.ACTOR),),
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.REJECTED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.REJECTED_BY.value,
        endpoint_rules=(_pair(EntityType.GOVERNANCE_DECISION, EntityType.ACTOR),),
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.BLOCKED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.BLOCKED_BY.value,
        endpoint_rules=tuple(
            _pair(source, target)
            for source in (
                EntityType.CANDIDATE,
                EntityType.EXPERIMENT,
                EntityType.JOB,
                EntityType.GOVERNANCE_DECISION,
            )
            for target in (
                EntityType.POLICY,
                EntityType.GOVERNANCE_DECISION,
                EntityType.DRIFT_ANALYSIS,
            )
        ),
        cardinality=Cardinality.MANY_TO_MANY,
    ),
    RelationshipType.GOVERNED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.GOVERNED_BY.value,
        endpoint_rules=tuple(
            _pair(entity_type, EntityType.POLICY)
            for entity_type in EntityType
            if entity_type != EntityType.POLICY
        ),
        cardinality=Cardinality.MANY_TO_MANY,
    ),
    RelationshipType.SUBMITTED_AS.value: RelationshipRule(
        relationship_type=RelationshipType.SUBMITTED_AS.value,
        endpoint_rules=tuple(
            _pair(entity_type, EntityType.JOB)
            for entity_type in EntityType
            if entity_type != EntityType.JOB
        ),
        cardinality=Cardinality.ZERO_OR_ONE_TO_ONE,
    ),
    RelationshipType.RESULTED_IN.value: RelationshipRule(
        relationship_type=RelationshipType.RESULTED_IN.value,
        endpoint_rules=(
            *(_pair(EntityType.JOB, target) for target in RESULT_TYPES),
            _pair(EntityType.REPLAY, EntityType.REPLAY_RESULT),
        ),
        cardinality=Cardinality.ZERO_OR_ONE_TO_MANY,
    ),
    RelationshipType.AUDITED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.AUDITED_BY.value,
        endpoint_rules=tuple(
            _pair(entity_type, EntityType.MCP_AUDIT_RECORD)
            for entity_type in EntityType
            if entity_type != EntityType.MCP_AUDIT_RECORD
        ),
        cardinality=Cardinality.ZERO_OR_ONE_TO_MANY,
    ),
    RelationshipType.REFERENCES_RESOURCE.value: RelationshipRule(
        relationship_type=RelationshipType.REFERENCES_RESOURCE.value,
        endpoint_rules=tuple(
            _pair(EntityType.MCP_AUDIT_RECORD, target)
            for target in RESOURCE_REFERENCE_TYPES
        ),
        cardinality=Cardinality.MANY_TO_MANY,
    ),
    RelationshipType.REPLAY_OF.value: RelationshipRule(
        relationship_type=RelationshipType.REPLAY_OF.value,
        endpoint_rules=(
            _pair(EntityType.REPLAY_INVESTIGATION, EntityType.WORKFLOW_EXECUTION),
            _pair(EntityType.REPLAY_INVESTIGATION, EntityType.EVALUATION_RESULT),
            _pair(EntityType.REPLAY_INVESTIGATION, EntityType.JOB),
            _pair(EntityType.REPLAY, EntityType.WORKFLOW_EXECUTION),
        ),
        cardinality=Cardinality.MANY_TO_ONE,
    ),
    RelationshipType.RECONSTRUCTS.value: RelationshipRule(
        relationship_type=RelationshipType.RECONSTRUCTS.value,
        endpoint_rules=(
            _pair(
                EntityType.REPLAY_INVESTIGATION,
                EntityType.WORKFLOW_EXECUTION,
                unique_per_source=True,
                unique_per_target=True,
            ),
        ),
        cardinality=Cardinality.ONE_TO_ONE,
    ),
    RelationshipType.OBSERVED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.OBSERVED_BY.value,
        endpoint_rules=(
            _pair(EntityType.WORKFLOW_EXECUTION, EntityType.EVALUATION_RESULT),
        ),
        cardinality=Cardinality.ONE_TO_MANY,
    ),
    RelationshipType.INVESTIGATES.value: RelationshipRule(
        relationship_type=RelationshipType.INVESTIGATES.value,
        endpoint_rules=tuple(
            _pair(source, target)
            for source in (
                EntityType.REPLAY_INVESTIGATION,
                EntityType.GOVERNANCE_INSIGHT,
            )
            for target in (
                EntityType.MCP_AUDIT_RECORD,
                EntityType.JOB,
                EntityType.EVALUATION_RESULT,
                EntityType.DRIFT_ANALYSIS,
            )
        ),
        cardinality=Cardinality.MANY_TO_MANY,
    ),
}


class RelationshipValidator:
    """
    Centralized relationship validator for ontology version 1.0.0.

    Validation rejects unknown relationship names, unsupported source or target
    types, invalid direction, and self-relationships unless the matching rule
    explicitly allows them.
    """

    def __init__(
        self,
        rules: dict[str, RelationshipRule] | None = None,
    ) -> None:
        self._rules = dict(rules or RULES)

    def rule_for(self, relationship_type: str) -> RelationshipRule:
        try:
            relationship_type = RelationshipType(relationship_type).value
        except ValueError as exc:
            raise InvalidOntologyRelationshipError(
                f"Unknown ontology relationship type: {relationship_type!r}."
            ) from exc

        try:
            return self._rules[relationship_type]
        except KeyError as exc:
            raise InvalidOntologyRelationshipError(
                f"No validation rule registered for {relationship_type}."
            ) from exc

    def endpoint_rule_for(
        self,
        relationship: OntologyRelationship,
    ) -> RelationshipEndpointRule:
        rule = self.rule_for(relationship.relationship_type)
        endpoint_rule = rule.endpoint_rule(
            source_type=relationship.source_entity_type,
            target_type=relationship.target_entity_type,
        )
        if endpoint_rule is None:
            allowed = ", ".join(
                sorted(
                    f"{item.source_type}->{item.target_type}"
                    for item in rule.endpoint_rules
                )
            )
            raise InvalidOntologyRelationshipError(
                "Invalid ontology relationship direction or endpoint types: "
                f"{relationship.source_entity_type} "
                f"{relationship.relationship_type} "
                f"{relationship.target_entity_type}. "
                f"Allowed pairs: {allowed}."
            )
        return endpoint_rule

    def validate(self, relationship: OntologyRelationship) -> None:
        endpoint_rule = self.endpoint_rule_for(relationship)
        if (
            relationship.source_entity_id == relationship.target_entity_id
            and relationship.source_entity_type == relationship.target_entity_type
            and not endpoint_rule.allow_self
        ):
            raise InvalidOntologyRelationshipError(
                "Ontology self-relationships are not allowed for "
                f"{relationship.relationship_type}."
            )
