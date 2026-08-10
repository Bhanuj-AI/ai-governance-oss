"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CircleDotDashed,
  DatabaseBackup,
  LoaderCircle,
  RefreshCcw,
  RotateCcw,
} from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SyncEventLifecycle } from "@/components/ontology-sync/SyncEventLifecycle";
import { AIGovernanceApiError } from "@/lib/api/client";
import {
  getOntologySyncEvent,
  getOntologySyncMetrics,
  listOntologySyncEvents,
  retryOntologySyncEvent,
} from "@/lib/api/ontology-sync";
import type {
  OntologySyncEvent,
  OntologySyncEventStatus,
  OntologySyncMetrics,
} from "@/types/ontology-sync";

type EventFilter = "DEAD_LETTER" | "FAILED" | "ALL";

const FILTERS: Array<{ value: EventFilter; label: string }> = [
  { value: "ALL", label: "All events" },
  { value: "DEAD_LETTER", label: "Dead letters" },
  { value: "FAILED", label: "Retrying failures" },
];

export function OntologySyncEventsPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<EventFilter>("DEAD_LETTER");
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  const metricsQuery = useQuery({
    queryKey: ["ontology-sync-metrics"],
    queryFn: getOntologySyncMetrics,
    refetchInterval: 10_000,
  });
  const eventsQuery = useQuery({
    queryKey: ["ontology-sync-events", filter],
    queryFn: () =>
      listOntologySyncEvents(
        { status: filter === "ALL" ? undefined : (filter as OntologySyncEventStatus) },
      ),
    refetchInterval: 10_000,
  });
  const events = eventsQuery.data ?? [];
  const resolvedSelectedEventId = selectedEventId ?? events[0]?.eventId ?? null;
  const selectedEventQuery = useQuery({
    queryKey: ["ontology-sync-event", resolvedSelectedEventId],
    queryFn: () => getOntologySyncEvent(resolvedSelectedEventId ?? ""),
    enabled: resolvedSelectedEventId !== null,
    refetchInterval: (query) =>
      query.state.data?.status === "PENDING" || query.state.data?.status === "PROCESSING"
        ? 3_000
        : false,
  });
  const selectedEvent = selectedEventQuery.data ?? events.find(
    (event) => event.eventId === resolvedSelectedEventId,
  );

  const retryMutation = useMutation({
    mutationFn: retryOntologySyncEvent,
    onSuccess: async (event) => {
      setSelectedEventId(event.eventId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["ontology-sync-events"] }),
        queryClient.invalidateQueries({ queryKey: ["ontology-sync-event", event.eventId] }),
        queryClient.invalidateQueries({ queryKey: ["ontology-sync-metrics"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] }),
      ]);
    },
  });

  return (
    <div className="h-[calc(100vh-4rem)] overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1360px] flex-col gap-5 px-6 py-5">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <DatabaseBackup className="h-5 w-5 text-primary" />
              <h1 className="text-2xl font-semibold">Sync events</h1>
            </div>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
              Review held graph updates and requeue them once the underlying issue is resolved.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void Promise.all([metricsQuery.refetch(), eventsQuery.refetch()]);
              if (resolvedSelectedEventId) {
                void selectedEventQuery.refetch();
              }
            }}
            disabled={metricsQuery.isFetching || eventsQuery.isFetching}
          >
            <RefreshCcw className="h-4 w-4" />
            Refresh
          </Button>
        </header>

        {metricsQuery.isLoading ? <StatePanel label="Loading synchronization metrics..." /> : null}
        {metricsQuery.isError ? <ErrorPanel error={metricsQuery.error} /> : null}
        {metricsQuery.data ? <MetricsGrid metrics={metricsQuery.data} /> : null}
        {selectedEvent ? <SyncEventLifecycle event={selectedEvent} /> : null}

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
          <Card>
            <CardHeader className="gap-3 pb-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="flex items-center gap-2">
                  <CircleDotDashed className="h-4 w-4 text-primary" />
                  Synchronization Events
                </CardTitle>
                <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span className="text-xs font-medium uppercase">Show</span>
                  <select
                    value={filter}
                    onChange={(event) => {
                      setSelectedEventId(null);
                      setFilter(event.target.value as EventFilter);
                    }}
                    className="h-8 rounded-md border border-input bg-background px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {FILTERS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p className="text-sm text-muted-foreground">
                Select an event to review it. Technical payload and reconciliation data stay
                collapsed until needed.
              </p>
            </CardHeader>
            <CardContent>
              {eventsQuery.isLoading ? <StatePanel label="Loading events..." compact /> : null}
              {eventsQuery.isError ? <ErrorPanel error={eventsQuery.error} /> : null}
              {!eventsQuery.isLoading && !eventsQuery.isError && events.length === 0 ? (
                <EmptyEvents filter={filter} />
              ) : null}
              {events.length ? (
                <div className="divide-y rounded-md border">
                  {events.map((event) => (
                    <EventRow
                      key={event.eventId}
                      event={event}
                      selected={event.eventId === resolvedSelectedEventId}
                      onSelect={() => setSelectedEventId(event.eventId)}
                    />
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <EventDetail
            event={selectedEvent}
            isLoading={selectedEventQuery.isLoading}
            error={selectedEventQuery.error}
            onRetry={(eventId) => retryMutation.mutate(eventId)}
            retrying={retryMutation.isPending}
            retryError={retryMutation.error}
          />
        </div>
      </div>
    </div>
  );
}

function MetricsGrid({ metrics }: { metrics: OntologySyncMetrics }) {
  const items = [
    [
      "Needs attention",
      metrics.deadLetterEvents + metrics.failedEvents,
      metrics.deadLetterEvents
        ? `${metrics.deadLetterEvents} event${metrics.deadLetterEvents === 1 ? "" : "s"} need${metrics.deadLetterEvents === 1 ? "s" : ""} a retry`
        : "No operator action required",
    ],
    [
      "In progress",
      metrics.pendingEvents + metrics.processingEvents,
      "Pending or currently synchronizing",
    ],
    ["Completed", metrics.completedEvents, `${metrics.totalEvents} retained event records`],
  ] as const;

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {items.map(([label, value, description]) => (
        <Card key={label} className="min-h-[104px]">
          <CardHeader className="pb-0">
            <CardTitle className="text-sm text-muted-foreground">{label}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">{value.toLocaleString()}</div>
            <p className="mt-1 text-xs leading-4 text-muted-foreground">{description}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function EventRow({
  event,
  selected,
  onSelect,
}: {
  event: OntologySyncEvent;
  selected: boolean;
  onSelect: () => void;
}) {
  const message = eventMessage(event);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`grid w-full gap-1.5 border-l-2 px-4 py-3.5 text-left transition-colors hover:bg-accent/40 ${selected ? "border-primary bg-primary/5" : "border-transparent"}`}
    >
      <div className="flex min-w-0 items-center justify-between gap-3">
        <span className="truncate text-sm font-medium">
          {event.entityType}
          {event.entityId ? ` · ${event.entityId}` : ""}
        </span>
        <StatusBadge status={event.status} />
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span>{event.eventType}</span>
        <span aria-hidden>·</span>
        <span className="text-muted-foreground">
          {event.retryCount} {event.retryCount === 1 ? "retry" : "retries"}
        </span>
        <span aria-hidden>·</span>
        <span>Updated {formatDate(event.updatedAt)}</span>
      </div>
      {message.error ? (
        <div className="truncate text-sm text-destructive">{message.text}</div>
      ) : null}
    </button>
  );
}

function EventDetail({
  event,
  isLoading,
  error,
  onRetry,
  retrying,
  retryError,
}: {
  event: OntologySyncEvent | undefined;
  isLoading: boolean;
  error: Error | null;
  onRetry: (eventId: string) => void;
  retrying: boolean;
  retryError: Error | null;
}) {
  const message = event ? eventMessage(event) : null;
  return (
    <Card className="h-fit xl:sticky xl:top-5">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <AlertCircle className="h-4 w-4 text-primary" />
          Event review
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {isLoading ? <StatePanel label="Loading event metadata..." compact /> : null}
        {error ? <ErrorPanel error={error} /> : null}
        {!isLoading && !error && !event ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Select an event to see the failure summary and available next action.
          </p>
        ) : null}
        {event ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <StatusBadge status={event.status} />
              {canRetry(event) ? (
                <Button
                  type="button"
                  size="sm"
                  onClick={() => onRetry(event.eventId)}
                  disabled={retrying}
                >
                  {retrying ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                  Requeue event
                </Button>
              ) : null}
            </div>
            {retryError ? <ErrorPanel error={retryError} /> : null}

            <DetailBlock
              title={message?.error ? "Failure summary" : "Synchronization result"}
              value={message?.text ?? null}
              error={message?.error}
            />

            <DetailsGrid
              fields={[
                ["Entity", `${event.entityType}${event.entityId ? ` / ${event.entityId}` : ""}`],
                ["Event type", event.eventType],
                ["Retry count", String(event.retryCount)],
                ["Last updated", formatDate(event.updatedAt)],
              ]}
            />

            <details className="group rounded-md border bg-muted/20 px-3 py-2.5">
              <summary className="cursor-pointer text-sm font-medium marker:text-muted-foreground">
                Technical details
              </summary>
              <div className="mt-4 space-y-4">
                <DetailsGrid
                  fields={[
                    ["Event ID", event.eventId, true],
                    ["Scope", event.scopeIdentifier ?? "Not scoped"],
                    ["Correlation ID", event.correlationId, true],
                    ["Created", formatDate(event.createdAt)],
                    ["Failed", formatOptionalDate(event.failedAt)],
                    ["Next retry", formatOptionalDate(event.nextRetryAt)],
                    ["Completed", formatOptionalDate(event.completedAt)],
                  ]}
                />
                <JsonBlock title="Event payload" value={event.payload} />
                <JsonBlock
                  title="Reconciliation report"
                  value={event.reconciliationReport}
                  emptyLabel="No reconciliation report was captured."
                />
              </div>
            </details>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

function DetailsGrid({ fields }: { fields: Array<[string, string, boolean?]> }) {
  return (
    <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
      {fields.map(([label, value, mono]) => (
        <div key={label} className="min-w-0">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className={`mt-1 break-words text-sm ${mono ? "font-mono text-xs" : ""}`}>{value}</div>
        </div>
      ))}
    </div>
  );
}

function DetailBlock({
  title,
  value,
  error = false,
}: {
  title: string;
  value: string | null;
  error?: boolean;
}) {
  return (
    <div>
      <h3 className="text-sm font-medium">{title}</h3>
      <div className={`mt-2 rounded-md border p-3 text-sm whitespace-pre-wrap ${error && value ? "border-destructive/30 bg-destructive/5 text-destructive" : "text-muted-foreground"}`}>
        {value ?? "No details were recorded."}
      </div>
    </div>
  );
}

function JsonBlock({
  title,
  value,
  emptyLabel = "No data was recorded.",
}: {
  title: string;
  value: Record<string, unknown> | null;
  emptyLabel?: string;
}) {
  return (
    <div>
      <h3 className="text-sm font-medium">{title}</h3>
      <pre className="mt-2 max-h-64 overflow-auto rounded-md border bg-muted/30 p-3 text-xs leading-5">
        {value ? JSON.stringify(value, null, 2) : emptyLabel}
      </pre>
    </div>
  );
}

function StatusBadge({ status }: { status: OntologySyncEventStatus }) {
  const classes: Record<OntologySyncEventStatus, string> = {
    PENDING: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
    PROCESSING: "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300",
    COMPLETED: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    FAILED: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    DEAD_LETTER: "border-destructive/30 bg-destructive/10 text-destructive",
    CANCELLED: "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-300",
  };
  return <Badge variant="outline" className={classes[status]}>{status.replaceAll("_", " ")}</Badge>;
}

function EmptyEvents({ filter }: { filter: EventFilter }) {
  const label = filter === "DEAD_LETTER" ? "dead-letter" : filter === "FAILED" ? "retrying failed" : "synchronization";
  return (
    <div className="rounded-md border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">
      No {label} events were found for this project.
    </div>
  );
}

function StatePanel({ label, compact = false }: { label: string; compact?: boolean }) {
  return (
    <div className={`flex items-center justify-center gap-2 rounded-md border text-sm text-muted-foreground ${compact ? "py-8" : "py-10"}`}>
      <LoaderCircle className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}

function ErrorPanel({ error }: { error: Error }) {
  const message = error instanceof AIGovernanceApiError ? `${error.code}: ${error.message}` : error.message;
  return (
    <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

function canRetry(event: OntologySyncEvent) {
  return event.status === "DEAD_LETTER" || event.status === "FAILED";
}

function eventMessage(event: OntologySyncEvent) {
  const failure = event.lastError ?? event.errorMessage;
  if (failure) return { text: failure, error: true };
  if (event.status === "COMPLETED") {
    return { text: "Synchronization completed successfully.", error: false };
  }
  if (event.status === "PROCESSING") {
    return { text: "Synchronization is currently in progress.", error: false };
  }
  if (event.status === "PENDING") {
    return { text: "Waiting for a synchronizer worker to pick up this event.", error: false };
  }
  if (event.status === "CANCELLED") {
    return { text: "This event was cancelled and retained for audit history.", error: false };
  }
  return { text: "No additional details were recorded.", error: false };
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function formatOptionalDate(value: string | null) {
  return value ? formatDate(value) : "Not recorded";
}
