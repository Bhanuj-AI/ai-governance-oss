"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, CircleAlert, Clock3, LoaderCircle, Play, ShieldAlert, XCircle } from "lucide-react";
import { useState } from "react";
import {
  GovernedEventFlow,
  type GovernedFlowStep,
  type GovernedFlowTone,
} from "@/components/governance/GovernedEventFlow";
import { ReplayLineageGraph } from "@/components/replays/ReplayLineageGraph";
import { ReplayStatusBadge } from "@/components/replays/ReplayStatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { archiveReplay, cancelReplay, evaluateReplay, getReplay, getReplayAudit, getReplayResult, submitReplay } from "@/lib/api/replays";
import { listProviderInstallations } from "@/lib/api/registries";
import { getCurrentContext } from "@/lib/api/tenancy";
import type { Replay, ReplayAuditRecord, ReplayResult } from "@/types/replay";

const TABS = ["Overview", "Configuration", "Execution", "Evaluation", "Comparison", "Lineage", "Audit"] as const;
type Tab = (typeof TABS)[number];

export function ReplayDetailPage({ replayId }: { replayId: string }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("Overview");
  const [reason, setReason] = useState("Studio operator request");
  const [providerInstallationId, setProviderInstallationId] = useState("");
  const [baselineStrategy, setBaselineStrategy] = useState<"EXPLICIT" | "LATEST_COMPATIBLE" | "SOURCE_PRIMARY">("LATEST_COMPATIBLE");
  const [baselineId, setBaselineId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const replay = useQuery({ queryKey: ["replay", replayId], queryFn: () => getReplay(replayId), refetchInterval: (query) => query.state.data && ["QUEUED", "RUNNING", "EVALUATING", "COMPARING"].includes(query.state.data.status) ? 5000 : false });
  const access = useQuery({ queryKey: ["current-context"], queryFn: getCurrentContext });
  const providerInstallations = useQuery({ queryKey: ["provider-installations"], queryFn: listProviderInstallations });
  const result = useQuery({ queryKey: ["replay-result", replayId], queryFn: () => getReplayResult(replayId), enabled: Boolean(replay.data?.result_id), retry: false });
  const audit = useQuery({ queryKey: ["replay-audit", replayId], queryFn: () => getReplayAudit(replayId), enabled: tab === "Audit", refetchInterval: () => tab === "Audit" && replay.data && ["QUEUED", "RUNNING", "EVALUATING", "COMPARING"].includes(replay.data.status) ? 5000 : false });
  const refresh = () => Promise.all([queryClient.invalidateQueries({ queryKey: ["replay", replayId] }), queryClient.invalidateQueries({ queryKey: ["replay-result", replayId] }), queryClient.invalidateQueries({ queryKey: ["replay-audit", replayId] })]);
  const mutationOptions = {
    onSuccess: () => { setError(null); void refresh(); },
    onError: (cause: Error) => setError(cause.message || "Replay action failed."),
  };
  const submit = useMutation({ ...mutationOptions, mutationFn: () => submitReplay(replayId, reason) });
  const cancel = useMutation({ ...mutationOptions, mutationFn: () => cancelReplay(replayId, reason) });
  const archive = useMutation({ ...mutationOptions, mutationFn: () => archiveReplay(replayId, reason) });
  const evaluate = useMutation({ ...mutationOptions, mutationFn: () => evaluateReplay(replayId, { reason, provider_installation_id: providerInstallationId || null, baseline_strategy: baselineStrategy, baseline_evaluation_id: baselineStrategy === "EXPLICIT" ? baselineId || null : null }) });

  if (replay.isLoading) return <div className="p-8 text-sm text-muted-foreground">Loading Replay…</div>;
  if (replay.isError || !replay.data) return <div className="p-8 text-sm text-destructive">Replay not found or unavailable in this tenant.</div>;
  const item = replay.data;
  const can = (permission: string) => access.data?.permissions.includes(permission) ?? false;

  return <div className="mx-auto flex w-full max-w-[1320px] flex-col gap-5 px-6 py-5">
    <Link href="/replays" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Replay Management</Link>
    <div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-3"><h1 className="text-2xl font-semibold">Replay {shortId(item.replay_id)}</h1><ReplayStatusBadge status={item.status} /></div><p className="mt-1 text-sm text-muted-foreground">Source execution <span className="font-mono">{item.source_execution_id}</span> · created by {item.requested_by}</p></div><HeaderActions replay={item} can={can} onSubmit={() => submit.mutate()} onEvaluate={() => evaluate.mutate()} onCancel={() => cancel.mutate()} onArchive={() => archive.mutate()} pending={submit.isPending || evaluate.isPending || cancel.isPending || archive.isPending} /></div>
    <div className="rounded-md border bg-muted/30 p-3 text-sm"><label className="mr-3 font-medium">Action Reason</label><input className="mt-2 h-9 w-full rounded-md border bg-background px-3 sm:mt-0 sm:w-[420px]" value={reason} onChange={(event) => setReason(event.target.value)} /></div>
    {item.status === "EXECUTION_COMPLETED" ? <Card><CardHeader><CardTitle>Evaluate Replay</CardTitle></CardHeader><CardContent className="grid gap-3 md:grid-cols-3"><select className="h-9 rounded-md border bg-background px-3" value={baselineStrategy} onChange={(event) => setBaselineStrategy(event.target.value as typeof baselineStrategy)}><option value="LATEST_COMPATIBLE">Latest compatible baseline</option><option value="SOURCE_PRIMARY">Source primary baseline</option><option value="EXPLICIT">Explicit baseline</option></select><select className="h-9 rounded-md border bg-background px-3" value={providerInstallationId} onChange={(event) => setProviderInstallationId(event.target.value)} disabled={providerInstallations.isLoading || providerInstallations.isError}><option value="">Use the replay&apos;s frozen provider</option>{(providerInstallations.data ?? []).filter((item) => item.enabled).map((installation) => <option key={installation.installation_id} value={installation.installation_id}>{installation.display_name} · {installation.provider_type}</option>)}</select>{baselineStrategy === "EXPLICIT" ? <input className="h-9 rounded-md border bg-background px-3" placeholder="Baseline evaluation ID" value={baselineId} onChange={(event) => setBaselineId(event.target.value)} /> : <div className="text-sm text-muted-foreground">The backend resolves compatibility and drift policy.</div>}{providerInstallations.isError ? <p className="text-xs text-destructive">Provider installations could not be loaded.</p> : null}</CardContent></Card> : null}
    {error ? <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div> : null}
    <div className="flex gap-1 overflow-x-auto border-b">{TABS.map((name) => <button key={name} type="button" className={`border-b-2 px-3 py-2 text-sm ${tab === name ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground"}`} onClick={() => setTab(name)}>{name}</button>)}</div>
    <ReplayTab tab={tab} replay={item} result={result.data} audit={audit.data} />
  </div>;
}

function HeaderActions({ replay, can, onSubmit, onEvaluate, onCancel, onArchive, pending }: { replay: Replay; can: (permission: string) => boolean; onSubmit: () => void; onEvaluate: () => void; onCancel: () => void; onArchive: () => void; pending: boolean }) {
  return <div className="flex flex-wrap gap-2">{replay.status === "READY" && can("replay.execute") ? <Button disabled={pending} onClick={onSubmit}><Play className="h-4 w-4" />Submit Replay</Button> : null}{replay.status === "EXECUTION_COMPLETED" && can("replay.evaluate") ? <Button disabled={pending} onClick={onEvaluate}>Evaluate Replay</Button> : null}{["READY", "QUEUED", "RUNNING", "EXECUTION_COMPLETED", "EVALUATING", "COMPARING"].includes(replay.status) && can("replay.cancel") ? <Button variant="outline" disabled={pending} onClick={onCancel}><XCircle className="h-4 w-4" />Cancel</Button> : null}{["READY", "EXECUTION_COMPLETED", "COMPLETED", "FAILED", "CANCELLED"].includes(replay.status) && can("replay.archive") ? <Button variant="outline" disabled={pending} onClick={onArchive}>Archive</Button> : null}{["FAILED", "CANCELLED", "COMPLETED"].includes(replay.status) ? <Button variant="outline" asChild><Link href={`/replays/new?source_execution_id=${encodeURIComponent(replay.source_execution_id)}`}>Create New Replay</Link></Button> : null}</div>;
}

function ReplayTab({ tab, replay, result, audit }: { tab: Tab; replay: Replay; result?: ReplayResult; audit?: ReplayAuditRecord[] }) {
  if (tab === "Configuration") return <Card><CardHeader><CardTitle>Frozen historical configuration</CardTitle></CardHeader><CardContent>{replay.configuration ? <pre className="max-h-[520px] overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(replay.configuration, null, 2)}</pre> : <Empty text="Configuration was not resolved for this replay." />}</CardContent></Card>;
  if (tab === "Execution") return <Card><CardHeader><CardTitle>Source and replay execution</CardTitle></CardHeader><CardContent className="grid gap-4 md:grid-cols-2"><Reference label="Source execution" value={replay.source_execution_id} /><Reference label="Replay execution" value={replay.replay_execution_id} /><Reference label="Execution job" value={replay.job_id} /><Reference label="Attempt count" value={String(replay.attempt_count)} /></CardContent></Card>;
  if (tab === "Evaluation") return <Card><CardHeader><CardTitle>Evaluation evidence</CardTitle></CardHeader><CardContent className="grid gap-4 md:grid-cols-2"><Reference label="Baseline evaluation" value={replay.baseline_evaluation_id} /><Reference label="Replay evaluation" value={replay.replay_evaluation_id} /><Reference label="Evaluation job" value={replay.evaluation_job_id} /><Reference label="Evaluation completed" value={formatDate(replay.evaluation_completed_at)} /></CardContent></Card>;
  if (tab === "Comparison") return <Comparison result={result} />;
  if (tab === "Lineage") return <Card><CardHeader><CardTitle>Replay lineage</CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-sm text-muted-foreground">Rendered from persisted Replay references. Ontology projection can enrich this graph but does not gate it.</p><ReplayLineageGraph replay={replay} result={result} /></CardContent></Card>;
  if (tab === "Audit") return <Card><CardHeader><CardTitle>Replay audit trail</CardTitle></CardHeader><CardContent><p className="mb-4 text-sm text-muted-foreground">Durable replay transitions and worker outcomes for this run. MCP tool activity remains available in the platform Audit area.</p>{audit ? <div className="space-y-2">{audit.length ? audit.map((record) => <div key={record.event_id} className="rounded-md border p-3 text-sm"><div className="flex flex-wrap items-center gap-x-2 gap-y-1"><span className="font-medium">{record.operation_type}</span><span className="text-muted-foreground">{record.status}</span><span className="text-muted-foreground">{formatDate(record.occurred_at)}</span></div><p className="mt-1 text-muted-foreground">{record.detail}</p><div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground"><span>{record.resource_type}: <span className="font-mono">{record.resource_id}</span></span>{record.job_id ? <span>Job: <span className="font-mono">{record.job_id}</span></span> : null}</div></div>) : <Empty text="No replay transitions have been recorded yet." />}</div> : <Empty text="Loading this replay’s durable audit trail…" />}</CardContent></Card>;
  return <Overview replay={replay} result={result} />;
}

function Overview({ replay, result }: { replay: Replay; result?: ReplayResult }) {
  return <div className="space-y-4">
    <ReplayLifecycle replay={replay} result={result} />
    <Card>
      <CardHeader><CardTitle>Replay Timing</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3"><Reference label="Created" value={formatDate(replay.created_at)} /><Reference label="Execution completed" value={formatDate(replay.execution_completed_at)} /><Reference label="Replay completed" value={formatDate(replay.completed_at)} /></div>
        {replay.failure ? <div className="rounded-md border border-destructive/30 bg-destructive/5 p-4"><div className="flex items-center gap-2 font-medium text-destructive"><ShieldAlert className="h-4 w-4" />{replay.failure.code}</div><p className="mt-1 text-sm">{replay.failure.message}</p><p className="mt-2 text-xs text-muted-foreground">Stage: {replay.failure.stage} · {formatDate(replay.failure.occurred_at)}</p></div> : null}
      </CardContent>
    </Card>
    {result ? <Comparison result={result} /> : <Card><CardContent><Empty text={replay.status === "COMPLETED" ? "Result evidence is loading." : "Comparison and drift evidence will appear after evaluation completes."} /></CardContent></Card>}
  </div>;
}

function ReplayLifecycle({ replay, result }: { replay: Replay; result?: ReplayResult }) {
  const presentation = replayPresentation(replay, result);
  const steps = replaySteps(replay, presentation.activeStep, presentation.tone);
  return <GovernedEventFlow stream="Replay / historical execution" steps={steps} outcomeLabel="Governed outcome" outcome={presentation.outcome} outcomeDetail={presentation.detail} outcomeTone={presentation.tone} activeStep={presentation.activeStep} activeAdornment={<ReplayStepState tone={presentation.tone} />} footer={<RunReferences replay={replay} result={result} />} />;
}

function replayPresentation(replay: Replay, result?: ReplayResult): { activeStep: number; outcome: string; detail: string; tone: Exclude<GovernedFlowTone, "muted"> } {
  if (replay.status === "COMPLETED" && result) {
    const severity = result.drift_summary.severity;
    const delta = result.comparison_summary.overall_score_delta;
    return { activeStep: 3, outcome: `COMPLETED · ${severity} DRIFT`, detail: `${result.drift_summary.changed_metrics.length} changed metric${result.drift_summary.changed_metrics.length === 1 ? "" : "s"}${delta === null ? "" : ` · score delta ${delta.toFixed(4)}`}.`, tone: severityTone(severity) };
  }
  if (replay.status === "FAILED") return { activeStep: stageIndex(replay.failure?.stage), outcome: "NEEDS REVIEW", detail: replay.failure?.message ?? "The replay did not complete. Review the recorded failure before retrying.", tone: "danger" };
  if (replay.status === "CANCELLED") return { activeStep: stageIndex(replay.failure?.stage), outcome: "CANCELLED", detail: "The replay was retained as durable evidence and was not allowed to continue on the live path.", tone: "warning" };
  if (replay.status === "ARCHIVED") return { activeStep: 3, outcome: "ARCHIVED", detail: "The completed replay and its evidence are retained for historical review.", tone: "warning" };
  if (replay.status === "DRAFT" || replay.status === "READY") return { activeStep: 0, outcome: "READY TO REPLAY", detail: "Source evidence is frozen and the replay can be submitted when the operator is ready.", tone: "info" };
  if (replay.status === "QUEUED") return { activeStep: 1, outcome: "QUEUED", detail: "A durable replay job is waiting for execution.", tone: "info" };
  if (replay.status === "RUNNING") return { activeStep: 2, outcome: "REPLAYING", detail: "A distinct historical execution is being produced without changing the source.", tone: "progress" };
  if (replay.status === "EXECUTION_COMPLETED") return { activeStep: 3, outcome: "READY TO EVALUATE", detail: "Replay execution evidence is ready to be evaluated against a compatible baseline.", tone: "info" };
  if (replay.status === "EVALUATING") return { activeStep: 3, outcome: "EVALUATING", detail: "Replay evidence is being evaluated before drift is compared.", tone: "progress" };
  if (replay.status === "COMPARING") return { activeStep: 3, outcome: "COMPARING DRIFT", detail: "Evaluation evidence is being compared with the compatible baseline.", tone: "progress" };
  return { activeStep: 3, outcome: "COMPLETED", detail: "Replay execution completed; outcome evidence is loading.", tone: "success" };
}

function replaySteps(replay: Replay, activeStep: number, activeTone: Exclude<GovernedFlowTone, "muted">): GovernedFlowStep[] {
  const steps: GovernedFlowStep[] = [
    { id: "freeze", label: "freeze source evidence", detail: "The approved historical source and configuration are resolved once.", tone: "info" },
    { id: "queue", label: "queue replay work", detail: replay.job_id ? "A durable execution job was created with an explicit source link." : "The replay is prepared for durable job creation.", tone: "progress" },
    { id: "execute", label: "produce replay execution", detail: "A distinct execution is produced; the original source remains unchanged.", tone: "info" },
    { id: "compare", label: "evaluate and compare", detail: "A compatible baseline is evaluated and semantic drift is retained as evidence.", tone: "success" },
  ];
  return steps.map((step, index) => ({ ...step, tone: index === activeStep ? activeTone : index > activeStep ? "muted" : step.tone }));
}

function RunReferences({ replay, result }: { replay: Replay; result?: ReplayResult }) {
  return <details><summary className="cursor-pointer text-sm font-medium">Run references</summary><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3"><Reference label="Source execution" value={replay.source_execution_id} /><Reference label="Replay execution" value={replay.replay_execution_id} /><Reference label="Execution job" value={replay.job_id} /><Reference label="Evaluation job" value={replay.evaluation_job_id} /><Reference label="Replay result" value={result?.result_id ?? replay.result_id} /><Reference label="Drift record" value={result?.drift_id ?? replay.drift_id} /></div></details>;
}

function ReplayStepState({ tone }: { tone: Exclude<GovernedFlowTone, "muted"> }) {
  if (tone === "success") return <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" aria-label="Completed" />;
  if (tone === "danger") return <CircleAlert className="h-3.5 w-3.5 text-destructive" aria-label="Needs review" />;
  if (tone === "progress") return <LoaderCircle className="h-3.5 w-3.5 animate-spin text-violet-600 dark:text-violet-400" aria-label="In progress" />;
  return <Clock3 className="h-3.5 w-3.5 text-cyan-600 dark:text-cyan-400" aria-label="Awaiting action" />;
}

function stageIndex(stage?: string) { const normalized = stage?.toLowerCase() ?? ""; if (normalized.includes("configuration") || normalized.includes("source")) return 0; if (normalized.includes("queue")) return 1; if (normalized.includes("execution") || normalized.includes("replay")) return 2; return 3; }
function severityTone(severity: string): Exclude<GovernedFlowTone, "muted"> { const normalized = severity.toUpperCase(); if (normalized === "CRITICAL" || normalized === "HIGH") return "danger"; if (normalized === "MEDIUM") return "warning"; return "success"; }
function Comparison({ result }: { result?: ReplayResult }) { if (!result) return <Card><CardHeader><CardTitle>Comparison & Drift</CardTitle></CardHeader><CardContent><Empty text="Comparison evidence is not available yet. The current backend response exposes compact result summaries and evidence references." /></CardContent></Card>; const c = result.comparison_summary; const d = result.drift_summary; return <Card><CardHeader><CardTitle>Comparison & Drift</CardTitle></CardHeader><CardContent className="space-y-4"><div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">{[["Metrics", c.metric_count], ["Improved", c.improved_metric_count], ["Regressed", c.regressed_metric_count], ["Unchanged", c.unchanged_metric_count], ["New", c.new_metric_count], ["Removed", c.removed_metric_count]].map(([label, value]) => <div key={String(label)} className="rounded-md border p-3"><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 text-lg font-semibold">{value}</div></div>)}</div><div className="grid gap-3 md:grid-cols-2"><Reference label="Overall score delta" value={c.overall_score_delta === null ? "Not available" : c.overall_score_delta.toFixed(4)} /><Reference label="Drift severity" value={d.severity} /><Reference label="Changed metrics" value={d.changed_metrics.join(", ") || "None"} /><Reference label="Analyzer version" value={d.analyzer_version} /></div><details><summary className="cursor-pointer text-sm font-medium">Effective drift threshold policy</summary><pre className="mt-2 overflow-auto rounded-md bg-muted p-3 text-xs">{JSON.stringify(d.threshold_policy, null, 2)}</pre></details></CardContent></Card>; }
function Reference({ label, value }: { label: string; value: string | null | undefined }) { return <div><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 break-all font-mono text-sm">{value || "Not available"}</div></div>; }
function Empty({ text }: { text: string }) { return <p className="py-5 text-sm text-muted-foreground">{text}</p>; }
function shortId(value: string) { return value.length > 16 ? `${value.slice(0, 10)}…${value.slice(-4)}` : value; }
function formatDate(value: string | null | undefined) { return value ? new Date(value).toLocaleString() : "Not reached"; }
