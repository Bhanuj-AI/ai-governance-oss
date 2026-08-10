import { aiGovernanceRequest } from "@/lib/api/client";
import { mapSubgraph } from "@/lib/api/graph";
import type {
  DecisionAuditRecord,
  DecisionAuditRecordDto,
  DecisionDetail,
  DecisionDetailDto,
  DecisionEvidence,
  DecisionEvidenceDto,
  DecisionEvidenceGraph,
  DecisionEvidenceGraphDto,
  DecisionEvidenceReference,
  DecisionEvidenceReferenceDto,
  DecisionExplanation,
  DecisionExplanationDto,
  DecisionList,
  DecisionListDto,
  DecisionLineage,
  DecisionLineageDto,
  DecisionPolicyReference,
  DecisionPolicyReferenceDto,
  GovernanceDecision,
  GovernanceDecisionDto,
  MissingEvidence,
  MissingEvidenceDto,
  PolicyOutcome,
  PolicyOutcomeDto,
  ReasoningEvidenceSummary,
  ReasoningEvidenceSummaryDto,
} from "@/types/decision";

export async function getDecisions(limit = 50) {
  const dto = await aiGovernanceRequest<DecisionListDto>("/api/v1/decisions", {
    limit,
  });
  return mapDecisionList(dto);
}

export async function getDecisionDetail(decisionId: string) {
  const dto = await aiGovernanceRequest<DecisionDetailDto>(
    `/api/v1/decisions/${encodeURIComponent(decisionId)}/detail`,
  );
  return mapDecisionDetail(dto);
}

export async function getDecisionEvidence(decisionId: string) {
  const dto = await aiGovernanceRequest<DecisionEvidenceDto>(
    `/api/v1/decisions/${encodeURIComponent(decisionId)}/evidence`,
  );
  return mapDecisionEvidence(dto);
}

export async function getDecisionExplanation(decisionId: string) {
  const dto = await aiGovernanceRequest<DecisionExplanationDto>(
    `/api/v1/decisions/${encodeURIComponent(decisionId)}/explanation`,
  );
  return mapDecisionExplanation(dto);
}

export async function getDecisionLineage(decisionId: string, depth = 2) {
  const dto = await aiGovernanceRequest<DecisionLineageDto>(
    `/api/v1/decisions/${encodeURIComponent(decisionId)}/lineage`,
    { depth },
  );
  return mapDecisionLineage(dto);
}

export function mapDecisionList(dto: DecisionListDto): DecisionList {
  return {
    decisions: dto.decisions.map(mapDecision),
  };
}

export function mapDecisionDetail(dto: DecisionDetailDto): DecisionDetail {
  return {
    decision: mapDecision(dto.decision),
    evidenceSummary: mapEvidenceSummary(dto.evidence_summary),
    policyOutcomes: dto.policy_outcomes.map(mapPolicyOutcome),
    auditRecords: dto.audit_records.map(mapAuditRecord),
  };
}

export function mapDecisionEvidence(dto: DecisionEvidenceDto): DecisionEvidence {
  return {
    decisionId: dto.decision_id,
    evidenceReferences: dto.evidence_references.map(mapEvidenceReference),
    evidenceGraph: mapEvidenceGraph(dto.evidence_graph),
  };
}

export function mapDecisionExplanation(
  dto: DecisionExplanationDto,
): DecisionExplanation {
  return {
    decisionId: dto.decision_id,
    summary: dto.summary,
    reasons: dto.reasons,
    evidenceReferences: dto.evidence_references.map(mapEvidenceReference),
    policyReferences: dto.policy_references.map(mapPolicyReference),
    missingEvidence: dto.missing_evidence.map(mapMissingEvidence),
    metadata: dto.metadata,
  };
}

export function mapDecisionLineage(dto: DecisionLineageDto): DecisionLineage {
  return {
    decision: mapDecision(dto.decision),
    subgraph: mapSubgraph(dto.subgraph),
  };
}

export function mapDecision(dto: GovernanceDecisionDto): GovernanceDecision {
  return {
    decisionId: dto.decision_id,
    decisionType: dto.decision_type,
    status: dto.status,
    target: {
      targetType: dto.target.target_type,
      targetId: dto.target.target_id,
    },
    reason: dto.reason,
    confidence: dto.confidence,
    evidence: dto.evidence.map(mapEvidenceReference),
    policies: dto.policies.map(mapPolicyReference),
    provenance: {
      producerType: dto.provenance.producer_type,
      producerId: dto.provenance.producer_id,
      actorId: dto.provenance.actor_id,
      correlationId: dto.provenance.correlation_id,
      requestId: dto.provenance.request_id,
      createdAt: dto.provenance.created_at,
    },
    supersession: {
      supersedesDecisionId: dto.supersession.supersedes_decision_id,
      supersededByDecisionId: dto.supersession.superseded_by_decision_id,
      supersessionReason: dto.supersession.supersession_reason,
    },
    metadata: dto.metadata,
    finalizedAt: dto.finalized_at,
    archivedAt: dto.archived_at,
  };
}

function mapEvidenceReference(
  dto: DecisionEvidenceReferenceDto,
): DecisionEvidenceReference {
  return {
    evidenceType: dto.evidence_type,
    evidenceId: dto.evidence_id,
    relationshipType: dto.relationship_type,
    source: dto.source,
    metadata: dto.metadata,
  };
}

function mapPolicyReference(
  dto: DecisionPolicyReferenceDto,
): DecisionPolicyReference {
  return {
    policyId: dto.policy_id,
    policyVersion: dto.policy_version,
    policyName: dto.policy_name,
    metadata: dto.metadata,
  };
}

function mapEvidenceGraph(
  dto: DecisionEvidenceGraphDto,
): DecisionEvidenceGraph {
  return {
    targetType: dto.target_type,
    targetId: dto.target_id,
    nodes: dto.nodes.map((node) => ({
      entityType: node.entity_type,
      entityId: node.entity_id,
      label: node.label,
      lifecycle: node.lifecycle,
      attributes: node.attributes,
      metadata: node.metadata,
    })),
    edges: dto.edges.map((edge) => ({
      relationshipType: edge.relationship_type,
      sourceType: edge.source_type,
      sourceId: edge.source_id,
      targetType: edge.target_type,
      targetId: edge.target_id,
      metadata: edge.metadata,
    })),
    missing: dto.missing.map(mapMissingEvidence),
    metadata: dto.metadata,
  };
}

function mapEvidenceSummary(
  dto: ReasoningEvidenceSummaryDto,
): ReasoningEvidenceSummary {
  return {
    targetType: dto.target_type,
    targetId: dto.target_id,
    metricScores: dto.metric_scores,
    metricFailures: dto.metric_failures,
    thresholdBreaches: dto.threshold_breaches,
    driftSeverity: dto.drift_severity,
    latestJobStatus: dto.latest_job_status,
    latestAuditStatus: dto.latest_audit_status,
    evaluationResultIds: dto.evaluation_result_ids,
    metricIds: dto.metric_ids,
    driftAnalysisIds: dto.drift_analysis_ids,
    leaderboardIds: dto.leaderboard_ids,
    jobIds: dto.job_ids,
    mcpAuditIds: dto.mcp_audit_ids,
    policyIds: dto.policy_ids,
    missingEvidence: dto.missing_evidence.map(mapMissingEvidence),
    metadata: dto.metadata,
  };
}

function mapPolicyOutcome(dto: PolicyOutcomeDto): PolicyOutcome {
  return {
    policyId: dto.policy_id,
    policyVersion: dto.policy_version,
    matchedRuleId: dto.matched_rule_id,
    effect: dto.effect,
    reason: dto.reason,
    matched: dto.matched,
    metadata: dto.metadata,
  };
}

function mapAuditRecord(dto: DecisionAuditRecordDto): DecisionAuditRecord {
  return {
    auditId: dto.audit_id,
    decisionId: dto.decision_id,
    action: dto.action,
    producerId: dto.producer_id,
    reason: dto.reason,
    actorId: dto.actor_id,
    correlationId: dto.correlation_id,
    requestId: dto.request_id,
    createdAt: dto.created_at,
    metadata: dto.metadata,
  };
}

function mapMissingEvidence(dto: MissingEvidenceDto): MissingEvidence {
  return {
    evidenceType: dto.evidence_type,
    reason: dto.reason,
    severity: dto.severity,
    metadata: dto.metadata,
  };
}
