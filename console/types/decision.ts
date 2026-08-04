import type { GraphSubgraph, GraphSubgraphDto } from "@/types/graph";

export type DecisionTarget = {
  targetType: string;
  targetId: string;
};

export type DecisionEvidenceReference = {
  evidenceType: string;
  evidenceId: string;
  relationshipType: string | null;
  source: string | null;
  metadata: Record<string, unknown>;
};

export type DecisionPolicyReference = {
  policyId: string;
  policyVersion: string;
  policyName: string | null;
  metadata: Record<string, unknown>;
};

export type DecisionProvenance = {
  producerType: string;
  producerId: string;
  actorId: string | null;
  correlationId: string | null;
  requestId: string | null;
  createdAt: string;
};

export type DecisionSupersession = {
  supersedesDecisionId: string | null;
  supersededByDecisionId: string | null;
  supersessionReason: string | null;
};

export type GovernanceDecision = {
  decisionId: string;
  decisionType: string;
  status: string;
  target: DecisionTarget;
  reason: string;
  confidence: string;
  evidence: DecisionEvidenceReference[];
  policies: DecisionPolicyReference[];
  provenance: DecisionProvenance;
  supersession: DecisionSupersession;
  metadata: Record<string, unknown>;
  finalizedAt: string | null;
  archivedAt: string | null;
};

export type MissingEvidence = {
  evidenceType: string;
  reason: string;
  severity: string;
  metadata: Record<string, unknown>;
};

export type EvidenceNode = {
  entityType: string;
  entityId: string;
  label: string | null;
  lifecycle: string | null;
  attributes: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

export type EvidenceEdge = {
  relationshipType: string;
  sourceType: string;
  sourceId: string;
  targetType: string;
  targetId: string;
  metadata: Record<string, unknown>;
};

export type DecisionEvidenceGraph = {
  targetType: string;
  targetId: string;
  nodes: EvidenceNode[];
  edges: EvidenceEdge[];
  missing: MissingEvidence[];
  metadata: Record<string, unknown>;
};

export type ReasoningEvidenceSummary = {
  targetType: string;
  targetId: string;
  metricScores: Record<string, number>;
  metricFailures: string[];
  thresholdBreaches: string[];
  driftSeverity: string | null;
  latestJobStatus: string | null;
  latestAuditStatus: string | null;
  evaluationResultIds: string[];
  metricIds: string[];
  driftAnalysisIds: string[];
  leaderboardIds: string[];
  jobIds: string[];
  mcpAuditIds: string[];
  policyIds: string[];
  missingEvidence: MissingEvidence[];
  metadata: Record<string, unknown>;
};

export type PolicyOutcome = {
  policyId: string;
  policyVersion: string;
  matchedRuleId: string | null;
  effect: string;
  reason: string;
  matched: boolean;
  metadata: Record<string, unknown>;
};

export type DecisionExplanation = {
  decisionId: string;
  summary: string;
  reasons: string[];
  evidenceReferences: DecisionEvidenceReference[];
  policyReferences: DecisionPolicyReference[];
  missingEvidence: MissingEvidence[];
  metadata: Record<string, unknown>;
};

export type DecisionAuditRecord = {
  auditId: string;
  decisionId: string;
  action: string;
  producerId: string;
  reason: string;
  actorId: string | null;
  correlationId: string | null;
  requestId: string | null;
  createdAt: string;
  metadata: Record<string, unknown>;
};

export type DecisionDetail = {
  decision: GovernanceDecision;
  evidenceSummary: ReasoningEvidenceSummary;
  policyOutcomes: PolicyOutcome[];
  auditRecords: DecisionAuditRecord[];
};

export type DecisionEvidence = {
  decisionId: string;
  evidenceReferences: DecisionEvidenceReference[];
  evidenceGraph: DecisionEvidenceGraph;
};

export type DecisionLineage = {
  decision: GovernanceDecision;
  subgraph: GraphSubgraph;
};

export type DecisionList = {
  decisions: GovernanceDecision[];
};

export type DecisionTargetDto = {
  target_type: string;
  target_id: string;
};

export type DecisionEvidenceReferenceDto = {
  evidence_type: string;
  evidence_id: string;
  relationship_type: string | null;
  source: string | null;
  metadata: Record<string, unknown>;
};

export type DecisionPolicyReferenceDto = {
  policy_id: string;
  policy_version: string;
  policy_name: string | null;
  metadata: Record<string, unknown>;
};

export type DecisionProvenanceDto = {
  producer_type: string;
  producer_id: string;
  actor_id: string | null;
  correlation_id: string | null;
  request_id: string | null;
  created_at: string;
};

export type DecisionSupersessionDto = {
  supersedes_decision_id: string | null;
  superseded_by_decision_id: string | null;
  supersession_reason: string | null;
};

export type GovernanceDecisionDto = {
  decision_id: string;
  decision_type: string;
  status: string;
  target: DecisionTargetDto;
  reason: string;
  confidence: string;
  evidence: DecisionEvidenceReferenceDto[];
  policies: DecisionPolicyReferenceDto[];
  provenance: DecisionProvenanceDto;
  supersession: DecisionSupersessionDto;
  metadata: Record<string, unknown>;
  finalized_at: string | null;
  archived_at: string | null;
};

export type MissingEvidenceDto = {
  evidence_type: string;
  reason: string;
  severity: string;
  metadata: Record<string, unknown>;
};

export type EvidenceNodeDto = {
  entity_type: string;
  entity_id: string;
  label: string | null;
  lifecycle: string | null;
  attributes: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

export type EvidenceEdgeDto = {
  relationship_type: string;
  source_type: string;
  source_id: string;
  target_type: string;
  target_id: string;
  metadata: Record<string, unknown>;
};

export type DecisionEvidenceGraphDto = {
  target_type: string;
  target_id: string;
  nodes: EvidenceNodeDto[];
  edges: EvidenceEdgeDto[];
  missing: MissingEvidenceDto[];
  metadata: Record<string, unknown>;
};

export type ReasoningEvidenceSummaryDto = {
  target_type: string;
  target_id: string;
  metric_scores: Record<string, number>;
  metric_failures: string[];
  threshold_breaches: string[];
  drift_severity: string | null;
  latest_job_status: string | null;
  latest_audit_status: string | null;
  evaluation_result_ids: string[];
  metric_ids: string[];
  drift_analysis_ids: string[];
  leaderboard_ids: string[];
  job_ids: string[];
  mcp_audit_ids: string[];
  policy_ids: string[];
  missing_evidence: MissingEvidenceDto[];
  metadata: Record<string, unknown>;
};

export type PolicyOutcomeDto = {
  policy_id: string;
  policy_version: string;
  matched_rule_id: string | null;
  effect: string;
  reason: string;
  matched: boolean;
  metadata: Record<string, unknown>;
};

export type DecisionExplanationDto = {
  decision_id: string;
  summary: string;
  reasons: string[];
  evidence_references: DecisionEvidenceReferenceDto[];
  policy_references: DecisionPolicyReferenceDto[];
  missing_evidence: MissingEvidenceDto[];
  metadata: Record<string, unknown>;
};

export type DecisionAuditRecordDto = {
  audit_id: string;
  decision_id: string;
  action: string;
  producer_id: string;
  reason: string;
  actor_id: string | null;
  correlation_id: string | null;
  request_id: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type DecisionDetailDto = {
  decision: GovernanceDecisionDto;
  evidence_summary: ReasoningEvidenceSummaryDto;
  policy_outcomes: PolicyOutcomeDto[];
  audit_records: DecisionAuditRecordDto[];
};

export type DecisionEvidenceDto = {
  decision_id: string;
  evidence_references: DecisionEvidenceReferenceDto[];
  evidence_graph: DecisionEvidenceGraphDto;
};

export type DecisionLineageDto = {
  decision: GovernanceDecisionDto;
  subgraph: GraphSubgraphDto;
};

export type DecisionListDto = {
  decisions: GovernanceDecisionDto[];
};
