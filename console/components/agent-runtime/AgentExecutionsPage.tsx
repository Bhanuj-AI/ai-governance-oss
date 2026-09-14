"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Bot, ChevronLeft, ChevronRight, CircleAlert, Clock3, Database, GitCompareArrows, Inbox, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { listAgentExecutions, listObservedAgents } from "@/lib/api/agent-runtime";
import type { AgentExecutionStatus, AgentExecutionSummary, ObservedAgent } from "@/types/agent-runtime";

const AGENT_PAGE_SIZE = 10;
const EXECUTION_PAGE_SIZE = 25;

export function AgentExecutionsPage({ demoDataPending = false }: { demoDataPending?: boolean }) {
  const router = useRouter();
  const [agentOffset, setAgentOffset] = useState(0);
  const [selectedAgentKey, setSelectedAgentKey] = useState<string>();
  const [comparisonExecutionIds, setComparisonExecutionIds] = useState<string[]>([]);
  const selectedAgentPanelRef = useRef<HTMLElement>(null);
  const shouldFocusSelectedAgentRef = useRef(false);
  const agentsQuery = useQuery({
    queryKey: ["runtime-agents", agentOffset],
    queryFn: () => listObservedAgents({ limit: AGENT_PAGE_SIZE, offset: agentOffset }),
    enabled: !demoDataPending,
  });
  const selectedAgent = agentsQuery.data?.items.find((agent) => observedAgentKey(agent) === selectedAgentKey) ?? agentsQuery.data?.items[0];
  const executionsQuery = useQuery({
    queryKey: ["agent-executions", "agent-detail", selectedAgent?.agentId, selectedAgent?.runtimeProvider],
    queryFn: () => listAgentExecutions({ agentId: selectedAgent?.agentId, runtimeProvider: selectedAgent?.runtimeProvider, limit: EXECUTION_PAGE_SIZE }),
    enabled: !demoDataPending && selectedAgent !== undefined,
  });

  function focusSelectedAgentPanel() {
    selectedAgentPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    selectedAgentPanelRef.current?.focus({ preventScroll: true });
  }

  useEffect(() => {
    if (!shouldFocusSelectedAgentRef.current || !selectedAgent) return;
    shouldFocusSelectedAgentRef.current = false;
    focusSelectedAgentPanel();
  }, [selectedAgent]);

  function selectAgent(agentKey: string) {
    if (selectedAgent && observedAgentKey(selectedAgent) === agentKey) {
      focusSelectedAgentPanel();
      return;
    }
    shouldFocusSelectedAgentRef.current = true;
    setSelectedAgentKey(agentKey);
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2"><Database className="h-4 w-4 text-primary" /><h2 className="font-semibold">Execution Evidence</h2></div>
          <p className="mt-1 text-sm text-muted-foreground">Select an observed agent to inspect its execution history and operational signals.</p>
        </div>
        {agentsQuery.isSuccess && <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">{agentsQuery.data.items.length} loaded</span>}
      </div>

      {demoDataPending && <EmptyState />}
      {!demoDataPending && agentsQuery.isLoading && <LoadingState label="Loading observed agents…" />}
      {!demoDataPending && agentsQuery.isError && <QueryError error={agentsQuery.error} label="agents" />}
      {!demoDataPending && agentsQuery.isSuccess && agentsQuery.data.items.length === 0 && <EmptyState />}

      {!demoDataPending && agentsQuery.isSuccess && agentsQuery.data.items.length > 0 && selectedAgent && (
        <>
          <section className="overflow-hidden rounded-xl border border-border/70 bg-card shadow-sm">
            <div className="flex items-center justify-between px-5 py-4">
              <div><h3 className="text-base font-semibold">Observed Agents</h3><p className="mt-1 text-sm text-muted-foreground">Choose an agent to inspect its execution evidence.</p></div>
              <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-foreground" onClick={() => void agentsQuery.refetch()}><RefreshCw className="h-3.5 w-3.5" />Refresh</Button>
            </div>
            <div className="hidden border-y border-border/60 bg-muted/20 px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground sm:grid sm:grid-cols-[minmax(0,1fr)_170px_120px_180px] sm:gap-x-4">
              <span>Agent</span><span>Runtime</span><span>Runs</span><span className="text-right">Last observed</span>
            </div>
            <div className="divide-y divide-border/60">
              {agentsQuery.data.items.map((agent) => {
                const agentKey = observedAgentKey(agent);
                const isSelected = agentKey === observedAgentKey(selectedAgent);
                return (
                  <button key={agentKey} type="button" onClick={() => selectAgent(agentKey)} aria-pressed={isSelected} aria-label={`Select ${agent.agentName || agent.agentId}; ${agent.executionCount} executions from ${agent.runtimeProvider}`}
                    className={`relative grid w-full grid-cols-[minmax(0,1fr)_auto] gap-x-4 px-5 py-4 text-left transition-colors focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyan-400 sm:grid-cols-[minmax(0,1fr)_170px_120px_180px] ${isSelected ? "bg-cyan-500/10 before:absolute before:inset-y-0 before:left-0 before:w-1 before:bg-cyan-500" : "hover:bg-muted/35"}`}>
                    <span className="flex min-w-0 items-center gap-3">
                      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${isSelected ? "bg-cyan-300 text-slate-950" : "bg-muted text-muted-foreground"}`}><Bot className="h-4 w-4" /></span>
                      <span className="min-w-0"><span className="block truncate text-[15px] font-semibold tracking-tight">{agent.agentName || agent.agentId}</span><span className="mt-0.5 block truncate font-mono text-xs text-muted-foreground">{agent.agentId}</span><span className="mt-1 block text-xs text-muted-foreground sm:hidden">{agent.runtimeProvider} · {agent.executionCount} {agent.executionCount === 1 ? "run" : "runs"}</span></span>
                    </span>
                    <span className="hidden self-center sm:block"><span className="inline-flex max-w-full truncate rounded-md border border-border/70 bg-muted/60 px-2 py-1 text-xs font-medium text-muted-foreground" title={agent.runtimeProvider}>{agent.runtimeProvider}</span></span>
                    <span className="hidden self-center sm:block"><span className="text-base font-semibold tabular-nums">{agent.executionCount}</span><span className="ml-1 text-xs text-muted-foreground">{agent.executionCount === 1 ? "run" : "runs"}</span></span>
                    <span className="self-center text-right text-xs text-muted-foreground" title={`Last observed ${formatDate(agent.lastStartedAt)}`}><span className="inline-flex items-center justify-end gap-1.5 whitespace-nowrap"><Clock3 className="h-3.5 w-3.5" />{formatDate(agent.lastStartedAt)}</span></span>
                  </button>
                );
              })}
            </div>
            <div className="flex items-center justify-between border-t border-border/60 bg-muted/10 px-5 py-3">
              <span className="text-xs text-muted-foreground">Page {Math.floor(agentOffset / AGENT_PAGE_SIZE) + 1}</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={agentOffset === 0} onClick={() => setAgentOffset(Math.max(0, agentOffset - AGENT_PAGE_SIZE))}><ChevronLeft className="h-3.5 w-3.5" />Previous</Button>
                <Button variant="outline" size="sm" disabled={agentsQuery.data.nextOffset === null} onClick={() => setAgentOffset(agentsQuery.data.nextOffset ?? agentOffset)}>Next<ChevronRight className="h-3.5 w-3.5" /></Button>
              </div>
            </div>
          </section>

          <section ref={selectedAgentPanelRef} tabIndex={-1} className="overflow-hidden rounded-lg border bg-card focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:ring-offset-2">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b bg-muted/20 px-4 py-4">
              <div><p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Selected agent</p><h3 className="mt-1 text-lg font-semibold">{selectedAgent.agentName || selectedAgent.agentId}</h3><p className="mt-0.5 font-mono text-xs text-muted-foreground">{selectedAgent.agentId} · {selectedAgent.runtimeProvider}</p></div>
              <div className="grid grid-cols-2 gap-x-5 gap-y-2 text-sm sm:grid-cols-4"><Metric label="Executions" value={selectedAgent.executionCount} /><Metric label="Succeeded" value={selectedAgent.succeededCount} /><Metric label="Failed" value={selectedAgent.failedCount} /><Metric label="Running" value={selectedAgent.runningCount} /></div>
            </div>
            <AgentOperationalMetrics executions={executionsQuery.data?.items ?? []} />
            {executionsQuery.isLoading && <LoadingState label="Loading agent executions…" compact />}
            {executionsQuery.isError && <div className="p-4"><QueryError error={executionsQuery.error} label="executions" /></div>}
            {executionsQuery.isSuccess && executionsQuery.data.items.length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">No execution records are available for this agent.</div>}
            {executionsQuery.isSuccess && executionsQuery.data.items.length > 0 && <ExecutionTable
              items={executionsQuery.data.items}
              comparisonExecutionIds={comparisonExecutionIds}
              onComparisonChange={setComparisonExecutionIds}
              onOpen={(executionId) => router.push(`/agents-runtime/executions/${encodeURIComponent(executionId)}`)}
              onCompare={(firstExecutionId, secondExecutionId) => router.push(`/agents-runtime/executions/compare/${encodeURIComponent(firstExecutionId)}/${encodeURIComponent(secondExecutionId)}`)}
            />}
          </section>
        </>
      )}
    </div>
  );
}

/**
 * Execution evidence aggregates an observed agent by its declared ID and the
 * runtime that produced it. Names are descriptive and are not an identity.
 */
function observedAgentKey(agent: Pick<ObservedAgent, "agentId" | "runtimeProvider">): string {
  return `${agent.agentId}\u0000${agent.runtimeProvider}`;
}

function ExecutionTable({ items, comparisonExecutionIds, onComparisonChange, onOpen, onCompare }: {
  items: AgentExecutionSummary[];
  comparisonExecutionIds: string[];
  onComparisonChange: (ids: string[]) => void;
  onOpen: (executionId: string) => void;
  onCompare: (firstExecutionId: string, secondExecutionId: string) => void;
}) {
  function toggleComparison(executionId: string) {
    if (comparisonExecutionIds.includes(executionId)) {
      onComparisonChange(comparisonExecutionIds.filter((id) => id !== executionId));
      return;
    }
    onComparisonChange([...comparisonExecutionIds.slice(-1), executionId]);
  }

  return <div className="overflow-x-auto"><div className="flex min-w-[42rem] items-center justify-between gap-3 border-b bg-muted/10 px-4 py-2.5"><p className="text-xs text-muted-foreground">Select up to two executions to compare their governed operational evidence.</p><Button variant="outline" size="sm" disabled={comparisonExecutionIds.length !== 2} onClick={() => onCompare(comparisonExecutionIds[0], comparisonExecutionIds[1])}><GitCompareArrows className="h-3.5 w-3.5" />Compare {comparisonExecutionIds.length}/2</Button></div><table className="w-full min-w-[42rem] text-sm"><thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="w-12 px-4 py-3 text-left font-medium"><span className="sr-only">Compare</span></th><th className="px-4 py-3 text-left font-medium">Execution</th><th className="px-4 py-3 text-left font-medium">Status</th><th className="px-4 py-3 text-left font-medium">Started</th><th className="px-4 py-3 text-left font-medium">Duration</th><th className="px-4 py-3 text-left font-medium">Events</th></tr></thead><tbody className="divide-y">{items.map((item) => {
    const selectedForComparison = comparisonExecutionIds.includes(item.executionId);
    return <tr key={item.executionId} role="link" tabIndex={0} onClick={() => onOpen(item.executionId)} onKeyDown={(event) => { if (event.target !== event.currentTarget) return; if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpen(item.executionId); } }} className={`cursor-pointer outline-none hover:bg-muted/30 focus-visible:bg-primary/10 ${selectedForComparison ? "bg-primary/5" : ""}`}><td className="px-4 py-3"><input type="checkbox" aria-label={`Compare ${item.externalExecutionId}`} checked={selectedForComparison} onClick={(event) => event.stopPropagation()} onChange={() => toggleComparison(item.executionId)} className="h-4 w-4 accent-primary" /></td><td className="px-4 py-3 font-mono text-xs text-muted-foreground">{item.externalExecutionId}</td><td className="px-4 py-3"><StatusBadge status={item.status} /></td><td className="px-4 py-3 text-xs text-muted-foreground">{formatDate(item.startedAt)}</td><td className="px-4 py-3 text-xs text-muted-foreground">{item.completedAt ? formatDuration(item.startedAt, item.completedAt) : "—"}</td><td className="px-4 py-3 text-xs text-muted-foreground"><span className="inline-flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" />{item.eventCount}</span></td></tr>;
  })}</tbody></table></div>;
}

function EmptyState() { return <div className="flex min-h-64 flex-col items-center justify-center rounded-lg border border-dashed bg-muted/20 px-6 text-center"><div className="flex h-10 w-10 items-center justify-center rounded-full bg-background text-muted-foreground shadow-sm"><Inbox className="h-5 w-5" /></div><span className="mt-3 text-sm font-semibold text-foreground">No observed agents yet</span><span className="mt-1 max-w-md text-sm text-muted-foreground">Execution evidence will appear here when agents send runtime traces. In local development, you can load the demo dataset to explore this view.</span></div>; }
function LoadingState({ label, compact = false }: { label: string; compact?: boolean }) { return <div className={`flex items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground ${compact ? "min-h-32" : "min-h-56"}`}>{label}</div>; }
function QueryError({ error, label }: { error: unknown; label: string }) { return <div role="alert" className="flex gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"><CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />{error instanceof Error ? error.message : `Failed to load ${label}.`}</div>; }
function AgentOperationalMetrics({ executions }: { executions: AgentExecutionSummary[] }) {
  const completed = executions.filter((execution) => execution.completedAt);
  const completedOutcomes = executions.filter((execution) => execution.status === "SUCCEEDED" || execution.status === "FAILED");
  const succeeded = completedOutcomes.filter((execution) => execution.status === "SUCCEEDED").length;
  const averageDurationSeconds = completed.length
    ? completed.reduce((total, execution) => total + durationSeconds(execution.startedAt, execution.completedAt), 0) / completed.length
    : null;
  const totalEvents = executions.reduce((total, execution) => total + execution.eventCount, 0);
  const cancelled = executions.filter((execution) => execution.status === "CANCELLED").length;

  return <div className="border-b bg-muted/10 px-4 py-3">
    <div className="flex flex-wrap items-end justify-between gap-2"><div><h4 className="text-sm font-medium">Operational Metrics</h4><p className="mt-0.5 text-xs text-muted-foreground">Calculated from the {executions.length} most recent execution record{executions.length === 1 ? "" : "s"} shown below.</p></div></div>
    <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Metric label="Success rate" value={completedOutcomes.length ? `${Math.round((succeeded / completedOutcomes.length) * 100)}%` : "—"} hint="Succeeded of completed outcomes" />
      <Metric label="Average duration" value={averageDurationSeconds === null ? "—" : formatSeconds(averageDurationSeconds)} hint="Terminal executions" />
      <Metric label="Observed events" value={totalEvents} hint="Across loaded records" />
      <Metric label="Cancelled" value={cancelled} hint="Loaded records" />
    </div>
  </div>;
}

function Metric({ label, value, hint }: { label: string; value: number | string; hint?: string }) { return <div><div className="text-xs text-muted-foreground">{label}</div><div className="mt-0.5 font-semibold">{value}</div>{hint && <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div>}</div>; }

function StatusBadge({ status }: { status: AgentExecutionStatus }) {
  const color = status === "RUNNING" ? "border-sky-200 bg-sky-300 text-slate-950" : status === "SUCCEEDED" ? "border-transparent bg-[#32d74b] text-[#1f2328]" : status === "FAILED" ? "border-transparent bg-[#ff453a] text-[#1f2328]" : status === "CANCELLED" ? "border-transparent bg-[#ff9f0a] text-[#1f2328]" : "border-border bg-muted text-muted-foreground";
  return <Badge variant="outline" className={`font-semibold ${color}`}>{status}</Badge>;
}
function formatDate(value: string) { return new Intl.DateTimeFormat("en-AU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }
function formatDuration(start: string, end: string | null) { if (!end) return "—"; const milliseconds = new Date(end).getTime() - new Date(start).getTime(); if (!Number.isFinite(milliseconds) || milliseconds < 0) return "—"; if (milliseconds < 1_000) return `${milliseconds}ms`; const seconds = Math.floor(milliseconds / 1_000); if (seconds < 60) return `${seconds}s`; const minutes = Math.floor(seconds / 60); return minutes < 60 ? `${minutes}m ${seconds % 60}s` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`; }
function durationSeconds(start: string, end: string | null) { return end ? Math.max(0, Math.floor((new Date(end).getTime() - new Date(start).getTime()) / 1000)) : 0; }
function formatSeconds(seconds: number) { if (seconds < 60) return `${Math.round(seconds)}s`; const minutes = Math.round(seconds / 60); return minutes < 60 ? `${minutes}m` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`; }
