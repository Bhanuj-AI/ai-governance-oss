export type InvocationAuditRecord = {
  invocationId: string;
  requestId: string;
  correlationId: string;
  toolName: string;
  actorId: string | null;
  clientId: string | null;
  status: string;
  authorizationDecision: string;
  errorCategory: string | null;
  startedAt: string;
  durationMs: number | null;
};

export type InvocationAuditPage = {
  records: InvocationAuditRecord[];
  total: number;
};
