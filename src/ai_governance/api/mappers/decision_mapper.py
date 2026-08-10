from __future__ import annotations

from ai_governance.api.models.decision import (
    DecisionAuditRecordResponse,
    DecisionDetailResponse,
    DecisionEvidenceGraphResponse,
    DecisionEvidenceReferenceResponse,
    DecisionEvidenceResponse,
    DecisionExplanationResponse,
    DecisionLineageResponse,
    DecisionListResponse,
    DecisionPolicyReferenceResponse,
    DecisionProvenanceResponse,
    DecisionResponse,
    DecisionSupersessionResponse,
    DecisionTargetResponse,
    EvidenceEdgeResponse,
    EvidenceNodeResponse,
    MissingEvidenceResponse,
    PolicyOutcomeResponse,
    ReasoningEvidenceSummaryResponse,
    ReasoningOutcomeResponse,
)
from ai_governance.api.models.ontology_graph import GraphSubgraphResponse
from ai_governance.decisions import (
    DecisionAuditRecord,
    DecisionEvidenceGraph,
    DecisionExplanation,
    GovernanceDecision,
    ReasoningEvidenceSummary,
)
from ai_governance.decisions.policies import PolicyEvaluationOutcome
from ai_governance.services.decision_application_service import (
    DecisionDetailResult,
    DecisionEvaluationResult,
    DecisionEvidenceResult,
    DecisionLineageResult,
    public_decision_metadata,
)


class DecisionApiMapper:
    """
    Converts decision application objects into REST DTOs.
    """

    @classmethod
    def to_reasoning_outcome_response(
        cls,
        result: DecisionEvaluationResult,
    ) -> ReasoningOutcomeResponse:
        return ReasoningOutcomeResponse(
            decision=cls.to_decision_response(result.decision),
            explanation=cls.to_explanation_response(result.explanation),
            evidence_summary=cls.to_evidence_summary_response(result.evidence_summary),
            policy_outcomes=[
                cls.to_policy_outcome_response(outcome)
                for outcome in result.policy_outcomes
            ],
        )

    @classmethod
    def to_detail_response(
        cls,
        result: DecisionDetailResult,
    ) -> DecisionDetailResponse:
        return DecisionDetailResponse(
            decision=cls.to_decision_response(result.decision),
            evidence_summary=cls.to_evidence_summary_response(result.evidence_summary),
            policy_outcomes=[
                cls.to_policy_outcome_response(outcome)
                for outcome in result.policy_outcomes
            ],
            audit_records=[
                cls.to_audit_record_response(record) for record in result.audit_records
            ],
        )

    @staticmethod
    def to_decision_response(
        decision: GovernanceDecision,
    ) -> DecisionResponse:
        return DecisionResponse(
            decision_id=decision.decision_id,
            decision_type=decision.decision_type.value,
            status=decision.status.value,
            target=DecisionTargetResponse(
                target_type=decision.target.target_type.value,
                target_id=decision.target.target_id,
            ),
            reason=decision.reason,
            confidence=decision.confidence.value,
            evidence=[
                DecisionEvidenceReferenceResponse(
                    evidence_type=reference.evidence_type,
                    evidence_id=reference.evidence_id,
                    relationship_type=reference.relationship_type,
                    source=reference.source,
                    metadata=dict(reference.metadata),
                )
                for reference in decision.evidence
            ],
            policies=[
                DecisionPolicyReferenceResponse(
                    policy_id=reference.policy_id,
                    policy_version=reference.policy_version,
                    policy_name=reference.policy_name,
                    metadata=dict(reference.metadata),
                )
                for reference in decision.policies
            ],
            provenance=DecisionProvenanceResponse(
                producer_type=decision.provenance.producer_type.value,
                producer_id=decision.provenance.producer_id,
                actor_id=decision.provenance.actor_id,
                correlation_id=decision.provenance.correlation_id,
                request_id=decision.provenance.request_id,
                created_at=decision.provenance.created_at,
            ),
            supersession=DecisionSupersessionResponse(
                supersedes_decision_id=(decision.supersession.supersedes_decision_id),
                superseded_by_decision_id=(
                    decision.supersession.superseded_by_decision_id
                ),
                supersession_reason=(decision.supersession.supersession_reason),
            ),
            metadata=public_decision_metadata(decision.metadata),
            finalized_at=decision.finalized_at,
            archived_at=decision.archived_at,
        )

    @classmethod
    def to_list_response(
        cls,
        decisions: tuple[GovernanceDecision, ...],
    ) -> DecisionListResponse:
        return DecisionListResponse(
            decisions=[cls.to_decision_response(decision) for decision in decisions]
        )

    @classmethod
    def to_evidence_response(
        cls,
        result: DecisionEvidenceResult,
    ) -> DecisionEvidenceResponse:
        return DecisionEvidenceResponse(
            decision_id=result.decision.decision_id,
            evidence_references=[
                DecisionEvidenceReferenceResponse(
                    evidence_type=reference.evidence_type,
                    evidence_id=reference.evidence_id,
                    relationship_type=reference.relationship_type,
                    source=reference.source,
                    metadata=dict(reference.metadata),
                )
                for reference in result.decision.evidence
            ],
            evidence_graph=cls.to_evidence_graph_response(result.evidence_graph),
        )

    @classmethod
    def to_evidence_graph_response(
        cls,
        graph: DecisionEvidenceGraph,
    ) -> DecisionEvidenceGraphResponse:
        return DecisionEvidenceGraphResponse(
            target_type=graph.target_type.value,
            target_id=graph.target_id,
            nodes=[
                EvidenceNodeResponse(
                    entity_type=node.entity_type,
                    entity_id=node.entity_id,
                    label=node.label,
                    lifecycle=node.lifecycle,
                    attributes=dict(node.attributes),
                    metadata=dict(node.metadata),
                )
                for node in graph.nodes
            ],
            edges=[
                EvidenceEdgeResponse(
                    relationship_type=edge.relationship_type,
                    source_type=edge.source_type,
                    source_id=edge.source_id,
                    target_type=edge.target_type,
                    target_id=edge.target_id,
                    metadata=dict(edge.metadata),
                )
                for edge in graph.edges
            ],
            missing=[
                MissingEvidenceResponse(
                    evidence_type=missing.evidence_type,
                    reason=missing.reason,
                    severity=missing.severity,
                    metadata=dict(missing.metadata),
                )
                for missing in graph.missing
            ],
            metadata=dict(graph.metadata),
        )

    @staticmethod
    def to_evidence_summary_response(
        summary: ReasoningEvidenceSummary,
    ) -> ReasoningEvidenceSummaryResponse:
        return ReasoningEvidenceSummaryResponse(
            target_type=summary.target_type.value,
            target_id=summary.target_id,
            metric_scores=dict(summary.metric_scores),
            metric_failures=list(summary.metric_failures),
            threshold_breaches=list(summary.threshold_breaches),
            drift_severity=summary.drift_severity,
            latest_job_status=summary.latest_job_status,
            latest_audit_status=summary.latest_audit_status,
            evaluation_result_ids=list(summary.evaluation_result_ids),
            metric_ids=list(summary.metric_ids),
            drift_analysis_ids=list(summary.drift_analysis_ids),
            leaderboard_ids=list(summary.leaderboard_ids),
            job_ids=list(summary.job_ids),
            mcp_audit_ids=list(summary.mcp_audit_ids),
            policy_ids=list(summary.policy_ids),
            missing_evidence=[
                MissingEvidenceResponse(
                    evidence_type=missing.evidence_type,
                    reason=missing.reason,
                    severity=missing.severity,
                    metadata=dict(missing.metadata),
                )
                for missing in summary.missing_evidence
            ],
            metadata=dict(summary.metadata),
        )

    @staticmethod
    def to_policy_outcome_response(
        outcome: PolicyEvaluationOutcome,
    ) -> PolicyOutcomeResponse:
        return PolicyOutcomeResponse(
            policy_id=outcome.policy_id,
            policy_version=outcome.policy_version,
            matched_rule_id=outcome.matched_rule_id,
            effect=outcome.effect.value,
            reason=outcome.reason,
            matched=outcome.matched,
            metadata=dict(outcome.metadata),
        )

    @staticmethod
    def to_audit_record_response(
        record: DecisionAuditRecord,
    ) -> DecisionAuditRecordResponse:
        return DecisionAuditRecordResponse(
            audit_id=record.audit_id,
            decision_id=record.decision_id,
            action=record.action.value,
            producer_id=record.producer_id,
            reason=record.reason,
            actor_id=record.actor_id,
            correlation_id=record.correlation_id,
            request_id=record.request_id,
            created_at=record.created_at,
            metadata=public_decision_metadata(record.metadata),
        )

    @staticmethod
    def to_explanation_response(
        explanation: DecisionExplanation,
    ) -> DecisionExplanationResponse:
        return DecisionExplanationResponse(
            decision_id=explanation.decision_id,
            summary=explanation.summary,
            reasons=list(explanation.reasons),
            evidence_references=[
                DecisionEvidenceReferenceResponse(
                    evidence_type=reference.evidence_type,
                    evidence_id=reference.evidence_id,
                    relationship_type=reference.relationship_type,
                    source=reference.source,
                    metadata=dict(reference.metadata),
                )
                for reference in explanation.evidence_references
            ],
            policy_references=[
                DecisionPolicyReferenceResponse(
                    policy_id=reference.policy_id,
                    policy_version=reference.policy_version,
                    policy_name=reference.policy_name,
                    metadata=dict(reference.metadata),
                )
                for reference in explanation.policy_references
            ],
            missing_evidence=[
                MissingEvidenceResponse(
                    evidence_type=missing.evidence_type,
                    reason=missing.reason,
                    severity=missing.severity,
                    metadata=dict(missing.metadata),
                )
                for missing in explanation.missing_evidence
            ],
            metadata=dict(explanation.metadata),
        )

    @classmethod
    def to_lineage_response(
        cls,
        result: DecisionLineageResult,
    ) -> DecisionLineageResponse:
        return DecisionLineageResponse(
            decision=cls.to_decision_response(result.decision),
            subgraph=GraphSubgraphResponse.from_domain(result.subgraph),
        )
