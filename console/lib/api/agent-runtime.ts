import { aiGovernanceJsonRequest, aiGovernanceRequest } from "@/lib/api/client";
import type {
  AgentExecutionList,
  AgentExecutionListDto,
  AgentExecutionDetailDto,
  AgentExecutionSummary,
  AgentExecutionSummaryDto,
  DetectionTriggerResponse,
  ReconcileResponse,
  RuntimeFinding,
  RuntimeFindingDto,
  RuntimeFindingList,
  RuntimeFindingListDto,
  ObservedAgent,
  ObservedAgentDto,
  ObservedAgentList,
  ObservedAgentListDto,
  CausalAuditDto,
  CausalAuditListDto,
  EvidenceInterventionPolicyCreateInput,
  EvidenceInterventionPolicyListDto,
  EvidenceInterventionPolicyPreviewDto,
  EvidenceInterventionPolicyPreviewInput,
  EvidenceInterventionPolicyDto,
  FindingReviewAction,
} from "@/types/agent-runtime";

export async function listCausalAudits({ agentId, classification, status, evaluatorRef, offset = 0, limit = 25 }: { agentId?: string; classification?: string; status?: string; evaluatorRef?: string; offset?: number; limit?: number } = {}): Promise<CausalAuditListDto> {
  return aiGovernanceRequest<CausalAuditListDto>("/api/v1/agents-runtime/causal-audits", {
    agent_id: agentId,
    classification,
    status,
    evaluator_ref: evaluatorRef,
    offset,
    limit,
  });
}

export async function getCausalAudit(auditId: string): Promise<CausalAuditDto> {
  return aiGovernanceRequest<CausalAuditDto>(
    `/api/v1/agents-runtime/causal-audits/${encodeURIComponent(auditId)}`,
  );
}

export async function listEvidenceInterventionPolicies(): Promise<EvidenceInterventionPolicyListDto> {
  return aiGovernanceRequest<EvidenceInterventionPolicyListDto>(
    "/api/v1/agents-runtime/causal-audit/intervention-policies",
  );
}

const interventionPolicyPath = "/api/v1/agents-runtime/causal-audit/intervention-policies";

export async function createEvidenceInterventionPolicy(input: EvidenceInterventionPolicyCreateInput): Promise<EvidenceInterventionPolicyDto> {
  return aiGovernanceJsonRequest<EvidenceInterventionPolicyDto, EvidenceInterventionPolicyCreateInput>(interventionPolicyPath, { method: "POST", body: input });
}

export async function validateEvidenceInterventionPolicy(policyId: string, version: number): Promise<EvidenceInterventionPolicyDto> {
  return aiGovernanceJsonRequest<EvidenceInterventionPolicyDto, undefined>(`${interventionPolicyPath}/${encodeURIComponent(policyId)}/versions/${version}/validate`, { method: "POST" });
}

export async function activateEvidenceInterventionPolicy(policyId: string, version: number): Promise<EvidenceInterventionPolicyDto> {
  return aiGovernanceJsonRequest<EvidenceInterventionPolicyDto, undefined>(`${interventionPolicyPath}/${encodeURIComponent(policyId)}/versions/${version}/activate`, { method: "POST" });
}

export async function retireEvidenceInterventionPolicy(policyId: string, version: number): Promise<EvidenceInterventionPolicyDto> {
  return aiGovernanceJsonRequest<EvidenceInterventionPolicyDto, undefined>(`${interventionPolicyPath}/${encodeURIComponent(policyId)}/versions/${version}/retire`, { method: "POST" });
}

export async function createEvidenceInterventionPolicyVersion(policyId: string, version: number, strategyConfiguration: Record<string, unknown>): Promise<EvidenceInterventionPolicyDto> {
  return aiGovernanceJsonRequest<EvidenceInterventionPolicyDto, { strategy_configuration: Record<string, unknown> }>(`${interventionPolicyPath}/${encodeURIComponent(policyId)}/versions/${version}/edit`, { method: "POST", body: { strategy_configuration: strategyConfiguration } });
}

export async function previewEvidenceInterventionPolicy(policyId: string, version: number, input: EvidenceInterventionPolicyPreviewInput): Promise<EvidenceInterventionPolicyPreviewDto> {
  return aiGovernanceJsonRequest<EvidenceInterventionPolicyPreviewDto, EvidenceInterventionPolicyPreviewInput>(`${interventionPolicyPath}/${encodeURIComponent(policyId)}/versions/${version}/preview`, { method: "POST", body: input });
}

export async function listObservedAgents({
  offset = 0,
  limit = 10,
}: {
  offset?: number;
  limit?: number;
} = {}): Promise<ObservedAgentList> {
  const dto = await aiGovernanceRequest<ObservedAgentListDto>(
    "/api/v1/agent-executions/agents",
    { offset, limit },
  );
  return {
    items: dto.items.map(mapObservedAgent),
    nextOffset: dto.next_offset,
  };
}

export async function listAgentExecutions({
  agentId,
  status,
  runtimeProvider,
  createdAfter,
  createdBefore,
  cursor,
  limit = 50,
}: {
  agentId?: string;
  status?: string;
  runtimeProvider?: string;
  createdAfter?: string;
  createdBefore?: string;
  cursor?: string;
  limit?: number;
} = {}) {
  const dto = await aiGovernanceRequest<AgentExecutionListDto>(
    "/api/v1/agent-executions",
    {
      agent_id: agentId,
      status,
      runtime_provider: runtimeProvider,
      created_after: createdAfter,
      created_before: createdBefore,
      cursor,
      limit,
    },
  );
  return mapExecutionList(dto);
}

/**
 * Returns the execution timeline used to select an observed, schema-described
 * tool result when authoring an intervention policy.
 */
export async function getAgentExecutionDetail(
  executionId: string,
): Promise<AgentExecutionDetailDto> {
  return aiGovernanceRequest<AgentExecutionDetailDto>(
    `/api/v1/agent-executions/${encodeURIComponent(executionId)}`,
  );
}

export async function triggerDetection(): Promise<DetectionTriggerResponse> {
  return aiGovernanceJsonRequest<DetectionTriggerResponse, undefined>(
    "/api/v1/runtime-findings/detect",
    { method: "POST" },
  );
}

export async function reconcileFindings(): Promise<ReconcileResponse> {
  return aiGovernanceJsonRequest<ReconcileResponse, undefined>(
    "/api/v1/runtime-findings/reconcile",
    { method: "POST" },
  );
}

export async function reviewRuntimeFinding(
  findingId: string,
  action: FindingReviewAction,
): Promise<RuntimeFinding> {
  const dto = await aiGovernanceJsonRequest<RuntimeFindingDto, { action: FindingReviewAction }>(
    `/api/v1/runtime-findings/${encodeURIComponent(findingId)}/review`,
    { method: "POST", body: { action } },
  );
  return mapFinding(dto);
}

export async function listRuntimeFindings({
  findingType,
  subjectType,
  subjectId,
  severity,
  status: statusFilter,
  limit = 50,
}: {
  findingType?: string;
  subjectType?: string;
  subjectId?: string;
  severity?: string;
  status?: string;
  limit?: number;
} = {}) {
  const dto = await aiGovernanceRequest<RuntimeFindingListDto>(
    "/api/v1/runtime-findings",
    {
      finding_type: findingType,
      subject_type: subjectType,
      subject_id: subjectId,
      severity,
      status: statusFilter,
      limit,
    },
  );
  return mapFindingList(dto);
}

function mapExecutionList(dto: AgentExecutionListDto): AgentExecutionList {
  return {
    items: dto.items.map(mapSummary),
    nextCursor: dto.next_cursor,
  };
}

function mapSummary(dto: AgentExecutionSummaryDto): AgentExecutionSummary {
  return {
    executionId: dto.execution_id,
    agentId: dto.agent_id,
    agentName: dto.agent_name,
    runtimeProvider: dto.runtime_provider,
    externalExecutionId: dto.external_execution_id,
    status: dto.status,
    startedAt: dto.started_at,
    completedAt: dto.completed_at,
    eventCount: dto.event_count,
  };
}

function mapObservedAgent(dto: ObservedAgentDto): ObservedAgent {
  return {
    agentId: dto.agent_id,
    agentName: dto.agent_name,
    runtimeProvider: dto.runtime_provider,
    executionCount: dto.execution_count,
    succeededCount: dto.succeeded_count,
    failedCount: dto.failed_count,
    runningCount: dto.running_count,
    lastStartedAt: dto.last_started_at,
  };
}

function mapFindingList(dto: RuntimeFindingListDto): RuntimeFindingList {
  return {
    items: dto.items.map(mapFinding),
  };
}

function mapFinding(dto: RuntimeFindingDto): RuntimeFinding {
  return {
    findingId: dto.finding_id,
    organizationId: dto.organization_id,
    projectId: dto.project_id,
    findingType: dto.finding_type,
    subjectType: dto.subject_type,
    subjectId: dto.subject_id,
    severity: dto.severity,
    status: dto.status,
    lifecycle: dto.lifecycle,
    baselineWindow: dto.baseline_window,
    observationWindow: dto.observation_window,
    baselineMetrics: dto.baseline_metrics.map((m) => ({
      name: m.name,
      value: m.value,
      sampleSize: m.sample_size,
    })),
    observedMetrics: dto.observed_metrics.map((m) => ({
      name: m.name,
      value: m.value,
      sampleSize: m.sample_size,
    })),
    observationCount: dto.observation_count,
    consecutiveNormalWindows: dto.consecutive_normal_windows,
    healthyReconciliationWindows: dto.healthy_reconciliation_windows,
    lastReconciliation: dto.last_reconciliation,
    reviews: dto.reviews,
    evidenceReferences: dto.evidence_references.map((r) => ({
      kind: r.kind,
      value: r.value,
    })),
    relatedExecutionIds: dto.related_execution_ids,
    detectorId: dto.detector_id,
    detectorVersion: dto.detector_version,
    firstDetectedAt: dto.first_detected_at,
    lastDetectedAt: dto.last_detected_at,
    resolvedAt: dto.resolved_at,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}
