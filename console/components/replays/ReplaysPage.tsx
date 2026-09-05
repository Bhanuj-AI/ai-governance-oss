"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  CircleCheckBig,
  ListFilter,
  Plus,
  RefreshCw,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CopyButton } from "@/components/ui/copy-button";
import { Card, CardContent } from "@/components/ui/card";
import { useTenantContext } from "@/components/tenancy/TenantContextProvider";
import { listCausalAudits } from "@/lib/api/agent-runtime";
import { getCurrentContext } from "@/lib/api/tenancy";
import { listReplays } from "@/lib/api/replays";
import { controlledCausalAuditId, isControlledCausalReplay } from "@/lib/replays/controlled-causal-replay";
import type { ReplayStatus } from "@/types/replay";
import { ReplayStatusBadge } from "./ReplayStatusBadge";

const PAGE_SIZE_OPTIONS = [10, 25, 50];
const statuses: ReplayStatus[] = [
  "DRAFT",
  "READY",
  "QUEUED",
  "RUNNING",
  "EXECUTION_COMPLETED",
  "EVALUATING",
  "COMPARING",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
  "ARCHIVED",
];
const active = new Set<ReplayStatus>([
  "QUEUED",
  "RUNNING",
  "EVALUATING",
  "COMPARING",
]);

export function ReplaysPage() {
  const router = useRouter();
  const search = useSearchParams();
  const tenant = useTenantContext();
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const status = search.get("status") ?? "";
  const sourceExecutionId = search.get("source_execution_id") ?? "";
  const requestedBy = search.get("requested_by") ?? "";
  const permissions = useQuery({
    queryKey: ["current-context", tenant.organizationId, tenant.projectId],
    queryFn: getCurrentContext,
  });
  const replays = useQuery({
    queryKey: ["replays", status, sourceExecutionId, requestedBy],
    queryFn: () =>
      listReplays({
        status,
        source_execution_id: sourceExecutionId,
        requested_by: requestedBy,
        limit: 200,
      }),
    refetchInterval: (query) =>
      query.state.data?.some((item) => active.has(item.status)) ? 5000 : false,
  });
  const canCreate = permissions.data?.permissions.includes("replay.create") ?? false;
  const items = useMemo(() => replays.data ?? [], [replays.data]);
  const causalAudits = useQuery({
    queryKey: ["causal-audits", "replay-outcomes"],
    queryFn: () => listCausalAudits({ limit: 100 }),
    enabled: items.some(isControlledCausalReplay),
  });
  const causalAuditsById = useMemo(
    () => new Map((causalAudits.data?.items ?? []).map((audit) => [audit.audit_id, audit])),
    [causalAudits.data],
  );
  const controlledCount = items.filter(isControlledCausalReplay).length;
  const activeCount = items.filter((item) => active.has(item.status)).length;
  const completedCount = items.filter((item) => item.status === "COMPLETED" || item.status === "EXECUTION_COMPLETED").length;
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(page, totalPages - 1);
  const visibleItems = items.slice(
    currentPage * pageSize,
    (currentPage + 1) * pageSize,
  );

  function updateFilter(name: string, value: string) {
    const params = new URLSearchParams(search.toString());
    if (value) {
      params.set(name, value);
    } else {
      params.delete(name);
    }
    setPage(0);
    router.replace(`/replays${params.size ? `?${params}` : ""}`);
  }

  return (
    <div className="studio-page flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Replay Operations</p>
          <h1 className="text-2xl font-semibold">Replay Management</h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
            Reproduce a historical execution safely. Controlled Causal Replays test governed evidence and publish their outcome to Causal Audit.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            className="border border-sky-200 bg-sky-300 text-slate-950 hover:bg-sky-200"
            onClick={() => void replays.refetch()}
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          {canCreate ? (
            <Button asChild className="border border-cyan-200 bg-cyan-300 text-slate-950 hover:bg-cyan-200">
              <Link href="/replays/new">
                <Plus className="h-4 w-4" />
                Create Replay
              </Link>
            </Button>
          ) : null}
        </div>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Replay overview">
        <ReplayMetric label="All" value={items.length} detail="In this project" />
        <ReplayMetric label="In Progress" value={activeCount} detail="Queued, running, or evaluating" tone="info" />
        <ReplayMetric label="Execution Complete" value={completedCount} detail="Outcome is ready or available" tone="success" />
        <ReplayMetric label="Controlled Causal" value={controlledCount} detail="Linked to Causal Audit" tone="causal" />
      </section>

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-2">
              <div className="mt-0.5 rounded-md bg-muted p-1.5 text-muted-foreground"><ListFilter className="h-4 w-4" /></div>
              <div><h2 className="font-semibold">Find Replay</h2><p className="mt-0.5 text-sm text-muted-foreground">Filter by lifecycle state, source execution, or requesting principal.</p></div>
            </div>
            <span className="rounded-full border bg-muted/20 px-2.5 py-1 text-xs text-muted-foreground">{items.length} matching replay{items.length === 1 ? "" : "s"}</span>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <select
              aria-label="Replay status"
              className="h-9 rounded-md border bg-background px-3 text-sm"
              value={status}
              onChange={(event) => updateFilter("status", event.target.value)}
            >
              <option value="">Status</option>
              {statuses.map((item) => (
                <option key={item} value={item}>
                  {item.replaceAll("_", " ")}
                </option>
              ))}
            </select>
            <input
              aria-label="Source execution ID"
              className="h-9 rounded-md border bg-background px-3 text-sm"
              placeholder="Source execution ID"
              value={sourceExecutionId}
              onChange={(event) =>
                updateFilter("source_execution_id", event.target.value)
              }
            />
            <input
              aria-label="Requested by"
              className="h-9 rounded-md border bg-background px-3 text-sm"
              placeholder="Requested by"
              value={requestedBy}
              onChange={(event) =>
                updateFilter("requested_by", event.target.value)
              }
            />
          </div>
          {replays.isLoading ? (
            <div className="py-10 text-sm text-muted-foreground">
              Loading replays…
            </div>
          ) : replays.isError ? (
            <div className="py-10 text-sm text-destructive">
              Unable to load replays. Check your access and selected tenant.
            </div>
          ) : items.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              {status || sourceExecutionId || requestedBy
                ? "No replays match the selected filters."
                : "No replays have been created for this project."}
              <div className="mt-3">
                {canCreate ? (
                  <Link className="text-primary hover:underline" href="/replays/new">
                    Create a replay from a historical workflow execution.
                  </Link>
                ) : null}
              </div>
            </div>
          ) : (
            <>
              <div className="overflow-hidden rounded-lg border">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/20 px-4 py-3">
                  <div><h2 className="font-semibold">Replay Runs</h2><p className="mt-0.5 text-sm text-muted-foreground">Open a run for technical detail, or follow a causal outcome directly.</p></div>
                  <span className="text-sm text-muted-foreground">Page {currentPage + 1} of {totalPages}</span>
                </div>
                <div className="overflow-x-auto">
                <table className="w-full min-w-[920px] text-left text-sm">
                  <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3">Replay</th>
                      <th className="px-4 py-3">Source execution</th>
                      <th className="px-4 py-3">Lifecycle</th>
                      <th className="px-4 py-3">Outcome</th>
                      <th className="px-4 py-3">Created</th>
                      <th className="px-4 py-3 text-right">Open</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleItems.map((replay) => {
                      const causalAuditId = controlledCausalAuditId(replay);
                      const controlledCausalReplay = causalAuditId !== null;
                      const causalAudit = causalAuditId ? causalAuditsById.get(causalAuditId) : undefined;
                      return (
                      <tr
                        key={replay.replay_id}
                        className="border-b last:border-0 hover:bg-accent/35"
                      >
                        <td className="px-4 py-3 align-top">
                          <div className="flex items-center gap-1.5"><Link className="font-medium hover:text-primary hover:underline" href={`/replays/${replay.replay_id}`}>{shortId(replay.replay_id)}</Link><CopyButton value={replay.replay_id} variant="ghost" size="sm" className="h-auto w-auto p-0 text-muted-foreground hover:text-foreground" copyTitle="Copy replay ID" iconClassName="h-3.5 w-3.5" /></div>
                          <div className="mt-1">{controlledCausalReplay ? <Badge variant="outline" className="border-cyan-200 bg-cyan-300 text-slate-950">Causal Replay</Badge> : <span className="text-xs text-muted-foreground">Historical replay</span>}</div>
                        </td>
                        <td className="max-w-64 px-4 py-3 align-top">
                          <div className="flex items-start gap-1"><span className="break-all font-mono text-xs leading-5">{replay.source_execution_id}</span><CopyButton value={replay.source_execution_id} variant="ghost" size="sm" className="mt-0.5 h-auto w-auto shrink-0 p-0 text-muted-foreground hover:text-foreground" copyTitle="Copy source execution ID" iconClassName="h-3.5 w-3.5" /></div>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <ReplayStatusBadge status={replay.status} />
                          <div className="mt-1 text-xs text-muted-foreground">{lifecycleHint(replay.status, controlledCausalReplay)}</div>
                        </td>
                        <td className="px-4 py-3 align-top">
                          {causalAuditId ? <CausalReplayOutcome auditId={causalAuditId} auditStatus={causalAudit?.status} loading={causalAudits.isLoading} /> : <ReplayOutcome status={replay.status} resultReady={Boolean(replay.result_id)} />}
                        </td>
                        <td className="px-4 py-3 align-top"><div>{formatDate(replay.created_at)}</div><div className="mt-1 text-xs text-muted-foreground">by {shortId(replay.requested_by)}</div></td>
                        <td className="px-4 py-3 text-right align-top">
                          <Button asChild size="sm" variant="outline"><Link href={`/replays/${replay.replay_id}`}>Details <ChevronRight className="h-3.5 w-3.5" /></Link></Button>
                        </td>
                      </tr>
                    );})}
                  </tbody>
                </table>
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1 text-sm">
                <span className="text-muted-foreground">
                  Page {currentPage + 1} of {totalPages} · {items.length} replays
                </span>
                <div className="flex items-center gap-2">
                  <label className="text-muted-foreground">Rows</label>
                  <select
                    className="h-8 rounded-md border bg-background px-2"
                    value={pageSize}
                    onChange={(event) => {
                      setPageSize(Number(event.target.value));
                      setPage(0);
                    }}
                  >
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={currentPage === 0}
                    onClick={() => setPage((value) => value - 1)}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={currentPage >= totalPages - 1}
                    onClick={() => setPage((value) => value + 1)}
                  >
                    Next
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function shortId(value: string) {
  return value.length > 16 ? `${value.slice(0, 10)}…${value.slice(-4)}` : value;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function ReplayMetric({ label, value, detail, tone = "default" }: { label: string; value: number; detail: string; tone?: "default" | "info" | "success" | "causal" }) {
  const toneClasses = tone === "success"
    ? { card: "border-emerald-400/60 bg-card hover:bg-emerald-500/5", label: "border-emerald-200 bg-emerald-300 text-slate-950" }
    : tone === "causal"
      ? { card: "border-cyan-400/60 bg-card hover:bg-cyan-500/5", label: "border-cyan-200 bg-cyan-300 text-slate-950" }
      : tone === "info"
        ? { card: "border-sky-400/60 bg-card hover:bg-sky-500/5", label: "border-sky-200 bg-sky-300 text-slate-950" }
        : { card: "border-border bg-card hover:bg-muted/20", label: "border-border bg-muted text-foreground" };
  return <div className={`rounded-lg border px-4 py-3 transition-colors ${toneClasses.card}`}><Badge variant="outline" className={toneClasses.label}>{label}</Badge><div className="mt-3 text-2xl font-semibold tabular-nums">{value}</div><div className="mt-1 text-xs text-muted-foreground">{detail}</div></div>;
}

function ReplayOutcome({ status, resultReady }: { status: ReplayStatus; resultReady: boolean }) {
  if (resultReady) return <div className="font-medium text-emerald-700 dark:text-emerald-300">Replay result ready</div>;
  if (status === "FAILED") return <div className="font-medium text-destructive">Needs review</div>;
  if (status === "CANCELLED") return <div className="font-medium text-amber-700 dark:text-amber-300">No outcome — cancelled</div>;
  if (status === "EXECUTION_COMPLETED") return <div><div className="font-medium">Ready to evaluate</div><div className="mt-1 text-xs text-muted-foreground">Choose a compatible baseline</div></div>;
  return <div className="text-muted-foreground">Outcome pending</div>;
}

function CausalReplayOutcome({ auditId, auditStatus, loading }: { auditId: string; auditStatus?: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED"; loading: boolean }) {
  const href = `/agents-runtime/causal-audits/${encodeURIComponent(auditId)}`;
  if (loading) return <div className="text-muted-foreground">Checking Causal Audit…</div>;
  if (auditStatus === "SUCCEEDED") return <div className="space-y-1"><div className="flex items-center gap-1.5 font-medium text-cyan-700 dark:text-cyan-300"><CircleCheckBig className="h-4 w-4" />Causal outcome recorded</div><Link className="text-sm text-cyan-700 hover:underline dark:text-cyan-300" href={href}>View evidence influence</Link></div>;
  if (auditStatus === "FAILED" || auditStatus === "CANCELLED") return <div className="space-y-1"><div className="font-medium text-destructive">Needs review</div><Link className="text-sm text-cyan-700 hover:underline dark:text-cyan-300" href={href}>Review audit diagnostics</Link></div>;
  if (auditStatus === "QUEUED" || auditStatus === "RUNNING") return <div className="space-y-1"><div className="font-medium">Causal audit in progress</div><Link className="text-sm text-cyan-700 hover:underline dark:text-cyan-300" href={href}>Open audit status</Link></div>;
  return <div className="space-y-1"><div className="font-medium text-muted-foreground">Causal audit unavailable</div><Link className="text-sm text-cyan-700 hover:underline dark:text-cyan-300" href={href}>Open audit diagnostics</Link></div>;
}

function lifecycleHint(status: ReplayStatus, controlledCausalReplay: boolean) {
  if (controlledCausalReplay && status === "EXECUTION_COMPLETED") return "Governed evidence replay completed";
  if (status === "COMPLETED") return "Evaluation and comparison completed";
  if (status === "FAILED") return "Open details for the failure";
  if (active.has(status)) return "Processing in the background";
  return status.replaceAll("_", " ").toLowerCase();
}
