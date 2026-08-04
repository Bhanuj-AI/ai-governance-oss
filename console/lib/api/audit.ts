import { kavachRequest, type QueryParams } from "@/lib/api/client";
import type {
  AuditDetail,
  AuditDetailDto,
  AuditFilterOptions,
  AuditFilterOptionsDto,
  AuditLinkedJob,
  AuditLinkedJobDto,
  AuditListItem,
  AuditListItemDto,
  AuditMetric,
  AuditMetricDto,
  AuditPage,
  AuditPageDto,
} from "@/types/audit";

export async function getAuditPage(params?: QueryParams) {
  const dto = await kavachRequest<AuditPageDto>("/api/v1/audit", params);
  return mapAuditPage(dto);
}

export async function getAuditDetail(auditId: string, params?: QueryParams) {
  const dto = await kavachRequest<AuditDetailDto>(
    `/api/v1/audit/${encodeURIComponent(auditId)}`,
    params,
  );
  return mapAuditDetail(dto);
}

function mapAuditPage(dto: AuditPageDto): AuditPage {
  return {
    summary: dto.summary.map(mapMetric),
    filters: mapFilterOptions(dto.filters),
    records: dto.records.map(mapListItem),
    total: dto.total,
    limit: dto.limit,
    offset: dto.offset,
  };
}

function mapAuditDetail(dto: AuditDetailDto): AuditDetail {
  return {
    auditId: dto.audit_id,
    requestId: dto.request_id,
    correlationId: dto.correlation_id,
    toolName: dto.tool_name,
    toolVersion: dto.tool_version,
    actorId: dto.actor_id,
    actorType: dto.actor_type,
    agentName: dto.agent_name,
    agentSessionId: dto.agent_session_id,
    clientName: dto.client_name,
    clientVersion: dto.client_version,
    idempotencyKey: dto.idempotency_key,
    operationType: dto.operation_type,
    resourceType: dto.resource_type,
    resourceId: dto.resource_id,
    requestHash: dto.request_hash,
    requestSummary: dto.request_summary,
    resolvedVersions: dto.resolved_versions,
    reason: dto.reason,
    dryRun: dto.dry_run,
    status: dto.status,
    jobId: dto.job_id,
    resultReference: dto.result_reference,
    errorCode: dto.error_code,
    errorMessage: dto.error_message,
    startedAt: dto.started_at,
    completedAt: dto.completed_at,
    durationMs: dto.duration_ms,
    metadata: dto.metadata,
    interrupted: dto.interrupted,
    interruptedReason: dto.interrupted_reason,
    linkedJob: dto.linked_job ? mapLinkedJob(dto.linked_job) : null,
    relatedRecords: dto.related_records.map(mapListItem),
  };
}

function mapMetric(dto: AuditMetricDto): AuditMetric {
  return {
    label: dto.label,
    value: dto.value,
    description: dto.description,
  };
}

function mapFilterOptions(dto: AuditFilterOptionsDto): AuditFilterOptions {
  return {
    statuses: dto.statuses,
    toolNames: dto.tool_names,
    actorIds: dto.actor_ids,
    resourceTypes: dto.resource_types,
    operationTypes: dto.operation_types,
  };
}

function mapListItem(dto: AuditListItemDto): AuditListItem {
  return {
    auditId: dto.audit_id,
    requestId: dto.request_id,
    correlationId: dto.correlation_id,
    toolName: dto.tool_name,
    operationType: dto.operation_type,
    resourceType: dto.resource_type,
    resourceId: dto.resource_id,
    actorId: dto.actor_id,
    status: dto.status,
    dryRun: dto.dry_run,
    startedAt: dto.started_at,
    completedAt: dto.completed_at,
    durationMs: dto.duration_ms,
    interrupted: dto.interrupted,
    interruptedReason: dto.interrupted_reason,
    reason: dto.reason,
    jobId: dto.job_id,
    jobStatus: dto.job_status,
    resultReference: dto.result_reference,
    errorCode: dto.error_code,
  };
}

function mapLinkedJob(dto: AuditLinkedJobDto): AuditLinkedJob {
  return {
    jobId: dto.job_id,
    jobType: dto.job_type,
    status: dto.status,
    submittedBy: dto.submitted_by,
    updatedAt: dto.updated_at,
  };
}
