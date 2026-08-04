import { kavachRequest, type QueryParams } from "@/lib/api/client";
import type { InvocationAuditPage } from "@/types/invocation-audit";

type InvocationAuditPageDto = {
  records: Array<{
    invocation_id: string;
    request_id: string;
    correlation_id: string;
    tool_name: string;
    actor_id: string | null;
    client_id: string | null;
    status: string;
    authorization_decision: string;
    error_category: string | null;
    started_at: string;
    duration_ms: number | null;
  }>;
  total: number;
};

export async function getInvocationAuditPage(
  params?: QueryParams,
): Promise<InvocationAuditPage> {
  const dto = await kavachRequest<InvocationAuditPageDto>(
    "/api/v1/audit/invocations",
    params,
  );
  return {
    total: dto.total,
    records: dto.records.map((record) => ({
      invocationId: record.invocation_id,
      requestId: record.request_id,
      correlationId: record.correlation_id,
      toolName: record.tool_name,
      actorId: record.actor_id,
      clientId: record.client_id,
      status: record.status,
      authorizationDecision: record.authorization_decision,
      errorCategory: record.error_category,
      startedAt: record.started_at,
      durationMs: record.duration_ms,
    })),
  };
}
