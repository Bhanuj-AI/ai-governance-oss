export type OntologySyncEventStatus =
  | "PENDING"
  | "PROCESSING"
  | "COMPLETED"
  | "FAILED"
  | "DEAD_LETTER"
  | "CANCELLED";

export type OntologySyncEventDto = {
  event_id: string;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  scope_identifier: string | null;
  correlation_id: string;
  payload: Record<string, unknown>;
  status: OntologySyncEventStatus;
  retry_count: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  error_message: string | null;
  next_retry_at: string | null;
  last_error: string | null;
  failed_at: string | null;
  reconciliation_report: Record<string, unknown> | null;
};

export type OntologySyncEventListDto = {
  events: OntologySyncEventDto[];
};

export type OntologySyncMetricsDto = {
  total_events: number;
  pending_events: number;
  processing_events: number;
  completed_events: number;
  failed_events: number;
  dead_letter_events: number;
  cancelled_events: number;
};

export type OntologySyncEvent = {
  eventId: string;
  eventType: string;
  entityType: string;
  entityId: string | null;
  scopeIdentifier: string | null;
  correlationId: string;
  payload: Record<string, unknown>;
  status: OntologySyncEventStatus;
  retryCount: number;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  errorMessage: string | null;
  nextRetryAt: string | null;
  lastError: string | null;
  failedAt: string | null;
  reconciliationReport: Record<string, unknown> | null;
};

export type OntologySyncMetrics = {
  totalEvents: number;
  pendingEvents: number;
  processingEvents: number;
  completedEvents: number;
  failedEvents: number;
  deadLetterEvents: number;
  cancelledEvents: number;
};
