"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQueries } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, FileWarning, GitCompareArrows, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getAgentExecutionDetail } from "@/lib/api/agent-runtime";
import type { AgentExecutionDetailDto, AgentExecutionEventDto, AgentExecutionStatus } from "@/types/agent-runtime";

type InspectorContentProps = {
  executionIds: string[];
  onClose: () => void;
};

function InspectorContent({ executionIds, onClose }: InspectorContentProps) {
  const details = useQueries({
    queries: executionIds.map((executionId) => ({
      queryKey: ["agent-executions", "detail", executionId],
      queryFn: () => getAgentExecutionDetail(executionId),
    })),
  });
  const isLoading = details.some((query) => query.isLoading);
  const hasError = details.some((query) => query.isError);
  const executions = details.flatMap((query) => query.data ? [query.data] : []);
  const comparing = executionIds.length === 2;

  return <div className="flex max-h-[min(52rem,calc(100vh-3rem))] flex-col bg-background">
    <div className="flex items-start justify-between gap-4 border-b px-6 py-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">Execution evidence</p>
        <h1 className="mt-1 text-xl font-semibold">{comparing ? "Compare executions" : "Execution inspector"}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{comparing ? "Compare governed operational facts and event coverage. Event payloads are intentionally not shown." : "Inspect the ordered runtime evidence captured for this execution. Event payloads are intentionally not shown."}</p>
      </div>
      <Button type="button" variant="ghost" size="icon" onClick={onClose} aria-label="Close execution inspector"><X className="h-4 w-4" /></Button>
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto p-6">
      {isLoading ? <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">Loading execution evidence…</div> : null}
      {hasError ? <div role="alert" className="flex gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />Execution evidence could not be loaded. It may no longer be available in the selected organization and project.</div> : null}
      {!isLoading && !hasError && executions.length === 1 ? <ExecutionDetail detail={executions[0]} /> : null}
      {!isLoading && !hasError && executions.length === 2 ? <ExecutionComparison details={executions} /> : null}
    </div>
    <div className="flex justify-end border-t px-6 py-4"><Button onClick={onClose}><CheckCircle2 className="h-4 w-4" />Done</Button></div>
  </div>;
}

function ExecutionDetail({ detail }: { detail: AgentExecutionDetailDto }) {
  const { execution, events, event_counts: eventCounts } = detail;
  return <div className="space-y-5">
    <section className="overflow-hidden rounded-lg border">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b bg-muted/20 px-4 py-4">
        <div><p className="font-mono text-xs text-muted-foreground">{execution.external_execution_id}</p><h2 className="mt-1 text-lg font-semibold">{execution.agent_name || execution.agent_id}</h2><p className="mt-0.5 text-sm text-muted-foreground">{execution.agent_id} · {execution.agent_version} · {execution.runtime_provider}</p></div>
        <StatusBadge status={execution.status} />
      </div>
      <div className="grid gap-x-5 gap-y-4 p-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Fact label="Started" value={formatDateTime(execution.started_at)} />
        <Fact label="Duration" value={formatDuration(execution.started_at, execution.completed_at)} />
        <Fact label="Events" value={String(events.length)} />
        <Fact label="Correlation" value={execution.correlation_id ?? "—"} mono />
        <Fact label="Parent execution" value={execution.parent_execution_id ?? "—"} mono />
        <Fact label="Execution ID" value={execution.execution_id} mono />
      </div>
    </section>
    <section className="rounded-lg border">
      <div className="border-b px-4 py-3"><h3 className="font-semibold">Evidence Coverage</h3><p className="mt-0.5 text-sm text-muted-foreground">The event types recorded by the runtime for this execution.</p></div>
      <div className="flex flex-wrap gap-2 p-4">{Object.entries(eventCounts).length ? Object.entries(eventCounts).map(([eventType, count]) => <Badge key={eventType} variant="outline">{humanize(eventType)} · {count}</Badge>) : <span className="text-sm text-muted-foreground">No event coverage is recorded.</span>}</div>
    </section>
    <section className="rounded-lg border">
      <div className="border-b px-4 py-3"><h3 className="font-semibold">Event Timeline</h3><p className="mt-0.5 text-sm text-muted-foreground">Operational facts, evidence references, and finalization status only.</p></div>
      <div className="divide-y">{events.length ? events.map((event) => <EventTimelineItem event={event} key={event.event_id} />) : <p className="p-6 text-center text-sm text-muted-foreground">No events were recorded for this execution.</p>}</div>
    </section>
  </div>;
}

function ExecutionComparison({ details }: { details: AgentExecutionDetailDto[] }) {
  const eventTypes = [...new Set(details.flatMap((detail) => Object.keys(detail.event_counts)))].sort();
  const metrics: Array<{ label: string; values: [string, string] }> = [
    { label: "Status", values: [details[0].execution.status, details[1].execution.status] },
    { label: "Agent", values: [details[0].execution.agent_name || details[0].execution.agent_id, details[1].execution.agent_name || details[1].execution.agent_id] },
    { label: "Runtime", values: [details[0].execution.runtime_provider, details[1].execution.runtime_provider] },
    { label: "Started", values: [formatDateTime(details[0].execution.started_at), formatDateTime(details[1].execution.started_at)] },
    { label: "Duration", values: [formatDuration(details[0].execution.started_at, details[0].execution.completed_at), formatDuration(details[1].execution.started_at, details[1].execution.completed_at)] },
    { label: "Recorded events", values: [String(details[0].events.length), String(details[1].events.length)] },
    { label: "Late events", values: [String(details[0].events.filter((event) => event.late_for_runtime_findings).length), String(details[1].events.filter((event) => event.late_for_runtime_findings).length)] },
  ];

  return <div className="space-y-5">
    <div className="grid gap-4 lg:grid-cols-2">{details.map((detail, index) => <section className="rounded-lg border" key={detail.execution.execution_id}><div className="border-b bg-muted/20 px-4 py-3"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">Execution {index + 1}</p><p className="mt-1 truncate font-mono text-sm" title={detail.execution.external_execution_id}>{detail.execution.external_execution_id}</p></div><div className="flex items-center justify-between gap-3 p-4"><div className="min-w-0"><p className="truncate font-medium">{detail.execution.agent_name || detail.execution.agent_id}</p><p className="mt-0.5 truncate text-xs text-muted-foreground">{detail.execution.runtime_provider}</p></div><StatusBadge status={detail.execution.status} /></div></section>)}</div>
    <section className="overflow-hidden rounded-lg border"><div className="flex items-center gap-2 border-b px-4 py-3"><GitCompareArrows className="h-4 w-4 text-primary" /><div><h2 className="font-semibold">Operational comparison</h2><p className="mt-0.5 text-sm text-muted-foreground">Differences are based only on recorded operational evidence.</p></div></div><div className="overflow-x-auto"><table className="w-full min-w-[42rem] text-sm"><thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-4 py-3">Fact</th>{details.map((detail) => <th className="px-4 py-3" key={detail.execution.execution_id}>{detail.execution.external_execution_id}</th>)}</tr></thead><tbody className="divide-y">{metrics.map((metric) => <tr key={metric.label}><td className="px-4 py-3 font-medium">{metric.label}</td><td className="px-4 py-3 text-muted-foreground">{metric.values[0]}</td><td className="px-4 py-3 text-muted-foreground">{metric.values[1]}</td></tr>)}</tbody></table></div></section>
    <section className="overflow-hidden rounded-lg border"><div className="border-b px-4 py-3"><h2 className="font-semibold">Event coverage comparison</h2><p className="mt-0.5 text-sm text-muted-foreground">A quick way to see which operational stages are present in one execution but absent in the other.</p></div><div className="overflow-x-auto"><table className="w-full min-w-[42rem] text-sm"><thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-4 py-3">Event type</th>{details.map((detail) => <th className="px-4 py-3" key={detail.execution.execution_id}>{detail.execution.external_execution_id}</th>)}</tr></thead><tbody className="divide-y">{eventTypes.map((eventType) => <tr key={eventType}><td className="px-4 py-3 font-medium">{humanize(eventType)}</td>{details.map((detail) => <td className="px-4 py-3 text-muted-foreground" key={detail.execution.execution_id}>{detail.event_counts[eventType] ?? 0}</td>)}</tr>)}</tbody></table></div></section>
  </div>;
}

function EventTimelineItem({ event }: { event: AgentExecutionEventDto }) {
  const operationalFacts = safeOperationalFacts(event.attributes);
  return <details className="group px-4 py-3" open={event.event_type === "ERROR"}><summary className="cursor-pointer list-none"><div className="flex flex-wrap items-start gap-x-3 gap-y-1"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted font-mono text-[11px] text-muted-foreground">{event.sequence_number}</span><div className="min-w-0 flex-1"><span className="font-medium">{humanize(event.event_type)}</span><span className="ml-2 text-xs text-muted-foreground">{formatDateTime(event.occurred_at)}</span></div>{event.late_for_runtime_findings ? <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"><FileWarning className="mr-1 h-3 w-3" />Late for findings</Badge> : null}</div></summary><div className="ml-9 mt-3 grid gap-3 border-l pl-4 text-sm sm:grid-cols-2">{operationalFacts.length ? <FactList title="Operational facts" entries={operationalFacts} /> : null}{event.actor_id || event.correlation_id || event.causation_id ? <FactList title="Trace links" entries={[["Actor", event.actor_id ? `${event.actor_type ?? "Actor"}: ${event.actor_id}` : null], ["Correlation", event.correlation_id], ["Caused by", event.causation_id]]} /> : null}{event.resource_references.length ? <ReferenceList title="Resources" references={event.resource_references} /> : null}{event.evidence_references.length ? <ReferenceList title="Evidence references" references={event.evidence_references} /> : null}{event.late_for_runtime_findings ? <div className="sm:col-span-2 rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-950 dark:text-amber-100"><span className="font-medium">Excluded from finalized runtime-finding windows.</span>{event.runtime_findings_finalization_cutoff_at ? ` The evidence window finalized at ${formatDateTime(event.runtime_findings_finalization_cutoff_at)}.` : ""}</div> : null}</div></details>;
}

function FactList({ title, entries }: { title: string; entries: Array<[string, string | null]> }) {
  return <div><p className="text-xs font-medium text-muted-foreground">{title}</p><dl className="mt-1.5 space-y-1">{entries.filter(([, value]) => value !== null).map(([label, value]) => <div className="flex gap-2" key={label}><dt className="shrink-0 text-xs text-muted-foreground">{label}</dt><dd className="break-all text-xs">{value}</dd></div>)}</dl></div>;
}

function ReferenceList({ title, references }: { title: string; references: string[] }) {
  return <div><p className="text-xs font-medium text-muted-foreground">{title}</p><ul className="mt-1.5 space-y-1">{references.map((reference) => <li className="break-all font-mono text-xs" key={reference}>{reference}</li>)}</ul></div>;
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className={`mt-0.5 break-all text-sm ${mono ? "font-mono text-xs" : "font-medium"}`}>{value}</dd></div>;
}

function StatusBadge({ status }: { status: AgentExecutionStatus }) {
  const color = status === "RUNNING" ? "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300" : status === "SUCCEEDED" ? "border-transparent bg-[#32d74b] text-[#1f2328]" : status === "FAILED" ? "border-destructive/30 bg-destructive/10 text-destructive" : status === "CANCELLED" ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300" : "border-border bg-muted text-muted-foreground";
  return <Badge variant="outline" className={`shrink-0 font-semibold ${color}`}>{status}</Badge>;
}

const SAFE_ATTRIBUTE_KEYS = new Set([
  "tool", "tool_id", "tool_name", "tool_call_id", "model", "model_id", "model_version", "policy", "policy_id", "decision_id", "evaluation_id", "evaluation_result_id", "evaluator", "evaluator_id", "status", "outcome", "result", "error_code", "error_type", "latency_ms", "duration_ms", "score", "success", "failure_reason_code",
]);

function safeOperationalFacts(attributes: Record<string, unknown>): Array<[string, string | null]> {
  return Object.entries(attributes).flatMap(([key, value]) => {
    if (!SAFE_ATTRIBUTE_KEYS.has(key) || !isSafeOperationalValue(value)) return [];
    return [[humanize(key), stringifyOperationalValue(value)]];
  });
}

function isSafeOperationalValue(value: unknown): value is string | number | boolean | null | Array<string | number | boolean | null> {
  return value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean" || (Array.isArray(value) && value.every((entry) => entry === null || typeof entry === "string" || typeof entry === "number" || typeof entry === "boolean"));
}

function stringifyOperationalValue(value: string | number | boolean | null | Array<string | number | boolean | null>) { return Array.isArray(value) ? value.map(String).join(", ") : value === null ? "null" : String(value); }
function humanize(value: string) { return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("en-AU", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
function formatDuration(start: string, end: string | null) { if (!end) return "Running"; const milliseconds = new Date(end).getTime() - new Date(start).getTime(); if (!Number.isFinite(milliseconds) || milliseconds < 0) return "—"; if (milliseconds < 1_000) return "<1s"; const seconds = Math.floor(milliseconds / 1_000); return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`; }

export function ExecutionInspectorModal({ executionIds }: { executionIds: string[] }) {
  const router = useRouter();
  return <Dialog.Root open onOpenChange={(open) => { if (!open) router.back(); }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(84rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-lg border bg-background shadow-xl focus:outline-none"><Dialog.Title className="sr-only">Execution inspector</Dialog.Title><Dialog.Description className="sr-only">Tenant-scoped execution evidence and a governed operational comparison.</Dialog.Description><InspectorContent executionIds={executionIds} onClose={() => router.back()} /></Dialog.Content></Dialog.Portal></Dialog.Root>;
}

export function ExecutionInspectorPage({ executionIds }: { executionIds: string[] }) {
  const router = useRouter();
  return <main className="mx-auto max-w-7xl p-6"><div className="overflow-hidden rounded-lg border shadow-sm"><InspectorContent executionIds={executionIds} onClose={() => router.replace("/agents-runtime")} /></div></main>;
}
