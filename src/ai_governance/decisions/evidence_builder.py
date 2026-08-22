from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ai_governance.decisions.enums import DecisionTargetType
from ai_governance.decisions.evidence import (
    DecisionEvidenceGraph,
    DecisionEvidenceSummary,
    EvidenceEdge,
    EvidenceNode,
    MissingEvidence,
)
from ai_governance.decisions.policies import PolicyEvaluationContext
from ai_governance.decisions.validation import coerce_enum, require_non_empty
from ai_governance.ontology import (
    EntityType,
    GraphEntity,
    GraphRelationship,
    GraphSubgraph,
    OntologyGraphQueryService,
    RelationshipType,
)

RELEVANT_ENTITY_TYPES = (
    EntityType.EVALUATION_RESULT.value,
    EntityType.EVALUATION_RUN.value,
    EntityType.METRIC.value,
    EntityType.EVALUATION_ARTIFACT.value,
    EntityType.EVALUATION_COMPARISON.value,
    EntityType.DRIFT_ANALYSIS.value,
    EntityType.LEADERBOARD.value,
    EntityType.LEADERBOARD_ENTRY.value,
    EntityType.JOB.value,
    EntityType.MCP_AUDIT_RECORD.value,
    EntityType.REPLAY_INVESTIGATION.value,
    EntityType.WORKFLOW_EXECUTION.value,
    EntityType.GOVERNANCE_INSIGHT.value,
    EntityType.GOVERNANCE_REPORT.value,
    EntityType.POLICY.value,
)

RELEVANT_RELATIONSHIP_TYPES = (
    RelationshipType.GENERATED_FROM.value,
    RelationshipType.HAS_RUN.value,
    RelationshipType.EXECUTES.value,
    RelationshipType.PRODUCES.value,
    RelationshipType.HAS_METRIC.value,
    RelationshipType.HAS_ARTIFACT.value,
    RelationshipType.EVALUATED_BY.value,
    RelationshipType.COMPARED_WITH.value,
    RelationshipType.CAUSED_DRIFT.value,
    RelationshipType.RESULTED_IN.value,
    RelationshipType.AUDITED_BY.value,
    RelationshipType.REFERENCES_RESOURCE.value,
    RelationshipType.REPLAY_OF.value,
    RelationshipType.RECONSTRUCTS.value,
    RelationshipType.OBSERVED_BY.value,
    RelationshipType.GOVERNED_BY.value,
    RelationshipType.BLOCKED_BY.value,
    RelationshipType.RECOMMENDS.value,
    RelationshipType.HAS_ENTRY.value,
    RelationshipType.RANKS.value,
)

DEFAULT_EVIDENCE_LIMIT = 500


class DecisionEvidenceBuilder:
    """
    Read-only builder for decision-ready evidence graphs and policy context.
    """

    def __init__(
        self,
        graph_query_service: OntologyGraphQueryService,
        *,
        limit: int = DEFAULT_EVIDENCE_LIMIT,
    ) -> None:
        self._graph_query_service = graph_query_service
        self._limit = limit

    def build_for_target(
        self,
        target_type: DecisionTargetType | str,
        target_id: str,
        *,
        depth: int = 3,
    ) -> DecisionEvidenceGraph:
        target_type = coerce_enum(
            "evidence builder target_type",
            DecisionTargetType,
            target_type,
        )
        require_non_empty("evidence builder target_id", target_id)

        target = self._graph_query_service.get_entity(
            target_type.value,
            target_id,
        )
        if target is None:
            return DecisionEvidenceGraph(
                target_type=target_type,
                target_id=target_id,
                missing=(
                    MissingEvidence(
                        evidence_type="Target",
                        reason="Target entity was not found.",
                        severity="CRITICAL",
                    ),
                ),
                metadata={"depth": depth, "target_found": False},
            )

        subgraph = self._graph_query_service.get_neighbourhood(
            target_type.value,
            target_id,
            depth=depth,
            relationship_types=RELEVANT_RELATIONSHIP_TYPES,
            entity_types=(target_type.value, *RELEVANT_ENTITY_TYPES),
            limit=self._limit,
        )
        nodes = self._evidence_nodes(subgraph, target)
        edges = self._evidence_edges(subgraph)
        missing = self._missing_evidence(nodes)
        if len(nodes) >= self._limit:
            missing = (
                *missing,
                MissingEvidence(
                    evidence_type="ResultLimit",
                    reason="Evidence graph reached the configured result limit.",
                    severity="WARNING",
                    metadata={"limit": self._limit},
                ),
            )

        return DecisionEvidenceGraph(
            target_type=target_type,
            target_id=target_id,
            nodes=nodes,
            edges=edges,
            missing=missing,
            metadata={
                "depth": depth,
                "limit": self._limit,
                "target_found": True,
            },
        )

    def summarize(
        self,
        evidence_graph: DecisionEvidenceGraph,
    ) -> DecisionEvidenceSummary:
        ids_by_type = self._ids_by_type(evidence_graph.nodes)
        return DecisionEvidenceSummary(
            target_type=evidence_graph.target_type,
            target_id=evidence_graph.target_id,
            evaluation_result_ids=ids_by_type[EntityType.EVALUATION_RESULT.value],
            metric_ids=ids_by_type[EntityType.METRIC.value],
            drift_analysis_ids=ids_by_type[EntityType.DRIFT_ANALYSIS.value],
            leaderboard_ids=ids_by_type[EntityType.LEADERBOARD.value],
            job_ids=ids_by_type[EntityType.JOB.value],
            mcp_audit_ids=ids_by_type[EntityType.MCP_AUDIT_RECORD.value],
            policy_ids=ids_by_type[EntityType.POLICY.value],
            missing=evidence_graph.missing,
            metadata=dict(evidence_graph.metadata),
        )

    def build_policy_context(
        self,
        evidence_graph: DecisionEvidenceGraph,
    ) -> PolicyEvaluationContext:
        context: dict[str, Any] = {
            "target": {
                "type": evidence_graph.target_type.value,
                "id": evidence_graph.target_id,
            },
            "metrics": {},
            "drift": {},
            "jobs": {},
            "audit": {},
        }
        for node in evidence_graph.nodes:
            if node.entity_type == EntityType.METRIC.value:
                self._map_metric(context, node)
            elif node.entity_type == EntityType.DRIFT_ANALYSIS.value:
                self._map_drift(context, node)
            elif node.entity_type == EntityType.JOB.value:
                self._map_latest_status(context["jobs"], node)
            elif node.entity_type == EntityType.MCP_AUDIT_RECORD.value:
                self._map_latest_status(context["audit"], node)

        return PolicyEvaluationContext(
            target_type=evidence_graph.target_type,
            target_id=evidence_graph.target_id,
            evidence=context,
            metadata={"source": "DecisionEvidenceBuilder"},
        )

    def _evidence_nodes(
        self,
        subgraph: GraphSubgraph,
        target: GraphEntity,
    ) -> tuple[EvidenceNode, ...]:
        graph_entities = {(target.entity_type, target.entity_id): target}
        for node in subgraph.nodes:
            graph_entities[
                (node.entity.entity_type, node.entity.entity_id)
            ] = node.entity
        return tuple(
            self._evidence_node(entity)
            for entity in sorted(
                graph_entities.values(),
                key=lambda item: (item.entity_type, item.entity_id),
            )
        )

    def _evidence_node(self, entity: GraphEntity) -> EvidenceNode:
        attributes = {
            **dict(entity.immutable_attributes),
            **dict(entity.mutable_attributes),
        }
        label = self._first_string(
            attributes,
            entity.metadata,
            ("label", "name", "metric_name", "display_name"),
        )
        return EvidenceNode(
            entity_type=entity.entity_type,
            entity_id=entity.entity_id,
            label=label,
            lifecycle=entity.lifecycle,
            attributes=attributes,
            metadata=dict(entity.metadata),
        )

    def _evidence_edges(
        self,
        subgraph: GraphSubgraph,
    ) -> tuple[EvidenceEdge, ...]:
        return tuple(
            self._evidence_edge(edge.relationship)
            for edge in sorted(
                subgraph.edges,
                key=lambda item: (
                    item.relationship.relationship_type,
                    item.relationship.source_entity_type,
                    item.relationship.source_entity_id,
                    item.relationship.target_entity_type,
                    item.relationship.target_entity_id,
                ),
            )
        )

    def _evidence_edge(
        self,
        relationship: GraphRelationship,
    ) -> EvidenceEdge:
        return EvidenceEdge(
            relationship_type=relationship.relationship_type,
            source_type=relationship.source_entity_type,
            source_id=relationship.source_entity_id,
            target_type=relationship.target_entity_type,
            target_id=relationship.target_entity_id,
            metadata=dict(relationship.metadata),
        )

    def _missing_evidence(
        self,
        nodes: tuple[EvidenceNode, ...],
    ) -> tuple[MissingEvidence, ...]:
        entity_types = {node.entity_type for node in nodes}
        missing = []
        if EntityType.EVALUATION_RESULT.value not in entity_types:
            missing.append(
                MissingEvidence(
                    evidence_type=EntityType.EVALUATION_RESULT.value,
                    reason="No evaluation result evidence is connected.",
                    severity="WARNING",
                )
            )
        if EntityType.METRIC.value not in entity_types:
            missing.append(
                MissingEvidence(
                    evidence_type=EntityType.METRIC.value,
                    reason="No metric evidence is connected.",
                    severity="WARNING",
                )
            )
        if EntityType.POLICY.value not in entity_types:
            missing.append(
                MissingEvidence(
                    evidence_type=EntityType.POLICY.value,
                    reason="No policy reference is connected.",
                    severity="INFO",
                )
            )
        return tuple(missing)

    def _ids_by_type(
        self,
        nodes: tuple[EvidenceNode, ...],
    ) -> dict[str, tuple[str, ...]]:
        result: dict[str, list[str]] = {
            entity_type: [] for entity_type in RELEVANT_ENTITY_TYPES
        }
        for node in nodes:
            if node.entity_type in result:
                result[node.entity_type].append(node.entity_id)
        return {
            entity_type: tuple(sorted(entity_ids))
            for entity_type, entity_ids in result.items()
        }

    def _map_metric(
        self,
        context: dict[str, Any],
        node: EvidenceNode,
    ) -> None:
        metric_name = self._first_string(
            node.attributes,
            node.metadata,
            ("metric_name", "name", "label"),
        )
        if metric_name is None:
            metric_name = node.entity_id
        metric_key = _normalize_key(metric_name)
        score = self._first_present(
            node.attributes,
            node.metadata,
            ("score", "value", "metric_value"),
        )
        metric_context: dict[str, Any] = {"id": node.entity_id}
        if score is not None:
            metric_context["score"] = score
        context["metrics"][metric_key] = metric_context

    def _map_drift(
        self,
        context: dict[str, Any],
        node: EvidenceNode,
    ) -> None:
        severity = self._first_present(
            node.attributes,
            node.metadata,
            ("severity", "drift_severity"),
        )
        if severity is not None:
            context["drift"]["severity"] = severity
        context["drift"]["id"] = node.entity_id

    def _map_latest_status(
        self,
        context: dict[str, Any],
        node: EvidenceNode,
    ) -> None:
        status = self._first_present(
            node.attributes,
            node.metadata,
            ("status", "lifecycle"),
        )
        if status is None:
            status = node.lifecycle
        context["latest_status"] = status
        context["latest_id"] = node.entity_id

    def _first_string(
        self,
        attributes: Mapping[str, Any],
        metadata: Mapping[str, Any],
        names: tuple[str, ...],
    ) -> str | None:
        value = self._first_present(attributes, metadata, names)
        return value if isinstance(value, str) and value.strip() else None

    def _first_present(
        self,
        attributes: Mapping[str, Any],
        metadata: Mapping[str, Any],
        names: tuple[str, ...],
    ) -> Any | None:
        for mapping in (attributes, metadata):
            for name in names:
                if name in mapping and mapping[name] is not None:
                    return mapping[name]
        return None


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")
