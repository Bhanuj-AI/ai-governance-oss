// Agent Runtime types — agent executions and runtime findings

export type AgentExecutionStatus =
  | "RECEIVED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED";

export type AgentExecutionDto = {
  execution_id: string;
  agent_id: string;
  agent_name: string;
  agent_version: string;
  external_execution_id: string;
  runtime_provider: string;
  status: AgentExecutionStatus;
  started_at: string;
  completed_at: string | null;
  correlation_id: string | null;
  parent_execution_id: string | null;
  metadata: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
};

export type AgentExecutionSummaryDto = {
  execution_id: string;
  agent_id: string;
  agent_name: string;
  runtime_provider: string;
  external_execution_id: string;
  status: AgentExecutionStatus;
  started_at: string;
  completed_at: string | null;
  event_count: number;
};

export type AgentExecutionListDto = {
  items: AgentExecutionSummaryDto[];
  next_cursor: string | null;
};

export type AgentExecutionEventDto = {
  event_id: string;
  execution_id: string;
  event_type: string;
  sequence_number: number;
  occurred_at: string;
  received_at: string;
  late_for_runtime_findings: boolean;
  runtime_findings_finalization_cutoff_at: string | null;
  runtime_findings_lateness_policy_hours: number | null;
  correlation_id: string | null;
  causation_id: string | null;
  actor_id: string | null;
  actor_type: string | null;
  step_id: string | null;
  step_name: string | null;
  lifecycle: "STARTED" | "COMPLETED" | "FAILED" | null;
  parent_step_id: string | null;
  source_kind: string | null;
  resource_references: string[];
  evidence_references: string[];
  attributes: Record<string, unknown>;
  event_schema_version: string;
};

export type AgentExecutionDetailDto = {
  execution: AgentExecutionDto;
  events: AgentExecutionEventDto[];
  event_counts: Record<string, number>;
};

export type AgentExecution = {
  executionId: string;
  agentId: string;
  agentName: string;
  agentVersion: string;
  externalExecutionId: string;
  runtimeProvider: string;
  status: AgentExecutionStatus;
  startedAt: string;
  completedAt: string | null;
  correlationId: string | null;
  parentExecutionId: string | null;
  metadata: Record<string, unknown>;
  version: number;
  createdAt: string;
  updatedAt: string;
};

export type AgentExecutionSummary = {
  executionId: string;
  agentId: string;
  agentName: string;
  runtimeProvider: string;
  externalExecutionId: string;
  status: AgentExecutionStatus;
  startedAt: string;
  completedAt: string | null;
  eventCount: number;
};

export type AgentExecutionList = {
  items: AgentExecutionSummary[];
  nextCursor: string | null;
};

export type ObservedAgentDto = {
  agent_id: string;
  agent_name: string;
  runtime_provider: string;
  execution_count: number;
  succeeded_count: number;
  failed_count: number;
  running_count: number;
  last_started_at: string;
};

export type ObservedAgentListDto = {
  items: ObservedAgentDto[];
  next_offset: number | null;
};

export type ObservedAgent = {
  agentId: string;
  agentName: string;
  runtimeProvider: string;
  executionCount: number;
  succeededCount: number;
  failedCount: number;
  runningCount: number;
  lastStartedAt: string;
};

export type ObservedAgentList = {
  items: ObservedAgent[];
  nextOffset: number | null;
};

// --- Runtime Findings ---

export type FindingSeverity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type FindingStatus = "OPEN" | "ACKNOWLEDGED" | "CLOSED" | "RESOLVED";
export type FindingLifecycle = "OPERATIONAL" | "CASE_REVIEW";
export type FindingReviewAction = "ACKNOWLEDGE" | "CLOSE";

export type MetricSnapshotDto = {
  name: string;
  value: number;
  sample_size: number;
};

export type EvidenceReferenceDto = {
  kind: string;
  value: string;
};

export type RuntimeFindingDto = {
  finding_id: string;
  organization_id: string;
  project_id: string | null;
  finding_type: string;
  subject_type: string;
  subject_id: string;
  severity: FindingSeverity;
  status: FindingStatus;
  lifecycle: FindingLifecycle;
  baseline_window: string;
  observation_window: string;
  baseline_metrics: MetricSnapshotDto[];
  observed_metrics: MetricSnapshotDto[];
  observation_count: number;
  consecutive_normal_windows: number;
  healthy_reconciliation_windows: ReconciliationWindowDto[];
  last_reconciliation: ReconciliationRecordDto | null;
  reviews: FindingReviewDto[];
  evidence_references: EvidenceReferenceDto[];
  related_execution_ids: string[];
  detector_id: string;
  detector_version: string;
  first_detected_at: string | null;
  last_detected_at: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RuntimeFindingListDto = {
  items: RuntimeFindingDto[];
};

export type RuntimeFinding = {
  findingId: string;
  organizationId: string;
  projectId: string | null;
  findingType: string;
  subjectType: string;
  subjectId: string;
  severity: FindingSeverity;
  status: FindingStatus;
  lifecycle: FindingLifecycle;
  baselineWindow: string;
  observationWindow: string;
  baselineMetrics: MetricSnapshot[];
  observedMetrics: MetricSnapshot[];
  observationCount: number;
  consecutiveNormalWindows: number;
  healthyReconciliationWindows: ReconciliationWindowDto[];
  lastReconciliation: ReconciliationRecordDto | null;
  reviews: FindingReviewDto[];
  evidenceReferences: EvidenceReference[];
  relatedExecutionIds: string[];
  detectorId: string;
  detectorVersion: string;
  firstDetectedAt: string | null;
  lastDetectedAt: string | null;
  resolvedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type RuntimeFindingList = {
  items: RuntimeFinding[];
};

export type MetricSnapshot = {
  name: string;
  value: number;
  sampleSize: number;
};

export type EvidenceReference = {
  kind: string;
  value: string;
};

export type FindingReviewDto = {
  action: FindingReviewAction;
  actor_id: string;
  reviewed_at: string;
  note: string | null;
};

export type DetectionTriggerResponse = {
  status: string;
  findingsCreated: number;
};

export type ReconcileResponse = {
  reconciled: number;
  resolved: number;
  processed: number;
  outcomes: Record<string, number>;
  findings: ReconciliationFindingDto[];
};

export type ReconciliationWindowDto = {
  observed_start: string;
  observed_end: string;
  baseline_start: string;
  baseline_end: string;
};

export type ReconciliationRecordDto = {
  window: ReconciliationWindowDto;
  outcome: string;
  reconciled_at: string;
  detail: string | null;
};

export type ReconciliationFindingDto = {
  finding_id: string;
  outcome: string;
  consecutive_normal_windows: number;
  required_normal_windows: number;
  window: ReconciliationWindowDto | null;
  detail: string | null;
};

// --- Causal Audit ---

export type CausalAuditClassification = "NO_TOOL_EVIDENCE" | "EVIDENCE_IGNORED" | "OVER_EXTENDED" | "EVIDENCE_ALIGNED";
export type CausalAuditStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";

export type CausalAuditDto = {
  audit_id: string;
  execution_id: string;
  agent_id: string;
  status: CausalAuditStatus;
  methodology_version: string;
  evaluator_ref: string;
  intervention_strategy: string;
  counterfactual_samples: number;
  intervention_policy_id: string | null;
  intervention_policy_version: number | null;
  classification: CausalAuditClassification | null;
  failure_code: string | null;
  failure_reason: string | null;
  created_at: string;
  completed_at: string | null;
  diagnostics: Record<string, unknown>;
  tool_call_results: Array<{
    tool_call_id: string;
    tool_name: string;
    position: number;
    intervention_strategy: string;
    intervention_strategy_version: string;
    intervention_seed: number | null;
    counterfactual_count: number;
    baseline_score: { value: number; method: string; provider: string; evaluator_version: string };
    counterfactual_score: { value: number; method: string; provider: string; evaluator_version: string };
    influence_score: number;
    useful: boolean;
    harmful: boolean;
    post_saturation: boolean;
    counterfactual_replay_ids: string[];
    counterfactual_execution_ids: string[];
    evidence_references: string[];
    intervention_provenance: Record<string, unknown>;
    counterfactual_lineage: Array<{
      replay_id: string;
      replay_execution_id: string;
      replay_status: string;
      policy_id: string;
      policy_version: number;
      provider_id: string;
      provider_version: string;
      original_evidence_digest: string;
      counterfactual_evidence_reference: string;
      counterfactual_evidence_digest: string;
      intervention_digest: string;
      evaluator_score: { value: number; method: string; provider: string; evaluator_version: string };
    }>;
  }>;
};

export type CausalAuditListDto = { items: CausalAuditDto[]; next_offset: number | null };

export type EvidenceInterventionPolicyDto = {
  policy_id: string;
  version: number;
  status: "DRAFT" | "ACTIVE" | "RETIRED";
  tool_name: string;
  schema_id: string;
  schema_version: string;
  provider_id: string;
  provider_version: string;
  allowed_strategies: string[];
  strategy_configuration: Record<string, unknown>;
  policy_digest: string;
  created_at: string;
  created_by: string;
  activated_at: string | null;
  activated_by: string | null;
  retired_at: string | null;
};

export type EvidenceInterventionPolicyListDto = { items: EvidenceInterventionPolicyDto[] };

export type EvidenceInterventionPolicyCreateInput = {
  tool_name: string;
  schema_id: string;
  schema_version: string;
  provider_id?: string;
  provider_version?: string;
  allowed_strategies: string[];
  strategy_configuration: Record<string, unknown>;
};

export type EvidenceInterventionPolicyPreviewInput = {
  execution_id: string;
  tool_call_id: string;
  strategy?: string;
  seed?: number;
};

export type EvidenceInterventionPolicyPreviewDto = {
  strategy: string;
  policy_id: string;
  policy_version: number;
  provider_id: string;
  provider_version: string;
  seed: number;
  original_evidence_digest: string;
  counterfactual_evidence_ref: string;
  counterfactual_evidence_digest: string;
  schema_valid: boolean;
  semantic_valid: boolean;
  material_difference: boolean;
  generation_metadata: Record<string, unknown>;
};
