export type AuditStatus =
  | "STARTED"
  | "SUCCEEDED"
  | "FAILED"
  | "DRY_RUN";

export type AuditMetricDto = {
  label: string;
  value: number;
  description: string | null;
};

export type AuditFilterOptionsDto = {
  statuses: string[];
  tool_names: string[];
  actor_ids: string[];
  resource_types: string[];
  operation_types: string[];
};

export type AuditListItemDto = {
  audit_id: string;
  request_id: string;
  correlation_id: string;
  tool_name: string;
  operation_type: string;
  resource_type: string;
  resource_id: string | null;
  actor_id: string;
  status: AuditStatus;
  dry_run: boolean;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  interrupted: boolean;
  interrupted_reason: string | null;
  reason: string;
  job_id: string | null;
  job_status: string | null;
  result_reference: string | null;
  error_code: string | null;
};

export type AuditLinkedJobDto = {
  job_id: string;
  job_type: string;
  status: string;
  submitted_by: string;
  updated_at: string;
};

export type AuditPageDto = {
  summary: AuditMetricDto[];
  filters: AuditFilterOptionsDto;
  records: AuditListItemDto[];
  total: number;
  limit: number;
  offset: number;
};

export type AuditDetailDto = {
  audit_id: string;
  request_id: string;
  correlation_id: string;
  tool_name: string;
  tool_version: string;
  actor_id: string;
  actor_type: string;
  agent_name: string | null;
  agent_session_id: string | null;
  client_name: string | null;
  client_version: string | null;
  idempotency_key: string;
  operation_type: string;
  resource_type: string;
  resource_id: string | null;
  request_hash: string;
  request_summary: Record<string, unknown>;
  resolved_versions: Record<string, unknown>;
  reason: string;
  dry_run: boolean;
  status: AuditStatus;
  job_id: string | null;
  result_reference: string | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  metadata: Record<string, unknown>;
  interrupted: boolean;
  interrupted_reason: string | null;
  linked_job: AuditLinkedJobDto | null;
  related_records: AuditListItemDto[];
};

export type AuditMetric = {
  label: string;
  value: number;
  description: string | null;
};

export type AuditFilterOptions = {
  statuses: string[];
  toolNames: string[];
  actorIds: string[];
  resourceTypes: string[];
  operationTypes: string[];
};

export type AuditListItem = {
  auditId: string;
  requestId: string;
  correlationId: string;
  toolName: string;
  operationType: string;
  resourceType: string;
  resourceId: string | null;
  actorId: string;
  status: AuditStatus;
  dryRun: boolean;
  startedAt: string;
  completedAt: string | null;
  durationMs: number | null;
  interrupted: boolean;
  interruptedReason: string | null;
  reason: string;
  jobId: string | null;
  jobStatus: string | null;
  resultReference: string | null;
  errorCode: string | null;
};

export type AuditLinkedJob = {
  jobId: string;
  jobType: string;
  status: string;
  submittedBy: string;
  updatedAt: string;
};

export type AuditPage = {
  summary: AuditMetric[];
  filters: AuditFilterOptions;
  records: AuditListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type AuditDetail = {
  auditId: string;
  requestId: string;
  correlationId: string;
  toolName: string;
  toolVersion: string;
  actorId: string;
  actorType: string;
  agentName: string | null;
  agentSessionId: string | null;
  clientName: string | null;
  clientVersion: string | null;
  idempotencyKey: string;
  operationType: string;
  resourceType: string;
  resourceId: string | null;
  requestHash: string;
  requestSummary: Record<string, unknown>;
  resolvedVersions: Record<string, unknown>;
  reason: string;
  dryRun: boolean;
  status: AuditStatus;
  jobId: string | null;
  resultReference: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  startedAt: string;
  completedAt: string | null;
  durationMs: number | null;
  metadata: Record<string, unknown>;
  interrupted: boolean;
  interruptedReason: string | null;
  linkedJob: AuditLinkedJob | null;
  relatedRecords: AuditListItem[];
};
