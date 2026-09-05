import {
  aiGovernanceJsonRequest,
  aiGovernanceRequest,
} from "@/lib/api/client";
import type {
  OntologySyncEvent,
  OntologySyncEventDto,
  OntologySyncEventListDto,
  OntologySyncEventStatus,
  OntologySyncMetrics,
  OntologySyncMetricsDto,
} from "@/types/ontology-sync";

const EVENTS_PATH = "/api/v1/ontology/synchronization/events";

type OntologySyncEventListFilters = {
  status?: OntologySyncEventStatus;
  entityType?: string;
  entityId?: string;
  limit?: number;
  offset?: number;
};

export async function listOntologySyncEventPage(
  filters: OntologySyncEventListFilters = {},
) {
  const dto = await aiGovernanceRequest<OntologySyncEventListDto>(EVENTS_PATH, {
    status: filters.status,
    entity_type: filters.entityType,
    entity_id: filters.entityId,
    limit: filters.limit ?? 25,
    offset: filters.offset ?? 0,
  });
  return {
    events: dto.events.map(mapEvent),
    limit: dto.limit,
    offset: dto.offset,
    hasMore: dto.has_more,
  };
}

export async function listOntologySyncEvents(
  filters: OntologySyncEventListFilters = {},
) {
  return (await listOntologySyncEventPage(filters)).events;
}

export async function getOntologySyncEvent(eventId: string) {
  const dto = await aiGovernanceRequest<OntologySyncEventDto>(
    `${EVENTS_PATH}/${encodeURIComponent(eventId)}`,
  );
  return mapEvent(dto);
}

export async function getOntologySyncMetrics() {
  const dto = await aiGovernanceRequest<OntologySyncMetricsDto>(
    `${EVENTS_PATH}/metrics`,
  );
  return mapMetrics(dto);
}

export async function retryOntologySyncEvent(eventId: string) {
  const dto = await aiGovernanceJsonRequest<OntologySyncEventDto, undefined>(
    `${EVENTS_PATH}/${encodeURIComponent(eventId)}/retry`,
    { method: "POST" },
  );
  return mapEvent(dto);
}

function mapEvent(dto: OntologySyncEventDto): OntologySyncEvent {
  return {
    eventId: dto.event_id,
    eventType: dto.event_type,
    entityType: dto.entity_type,
    entityId: dto.entity_id,
    scopeIdentifier: dto.scope_identifier,
    correlationId: dto.correlation_id,
    payload: dto.payload,
    status: dto.status,
    retryCount: dto.retry_count,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    completedAt: dto.completed_at,
    errorMessage: dto.error_message,
    nextRetryAt: dto.next_retry_at,
    lastError: dto.last_error,
    failedAt: dto.failed_at,
    reconciliationReport: dto.reconciliation_report,
  };
}

function mapMetrics(dto: OntologySyncMetricsDto): OntologySyncMetrics {
  return {
    totalEvents: dto.total_events,
    pendingEvents: dto.pending_events,
    processingEvents: dto.processing_events,
    completedEvents: dto.completed_events,
    failedEvents: dto.failed_events,
    deadLetterEvents: dto.dead_letter_events,
    cancelledEvents: dto.cancelled_events,
  };
}
