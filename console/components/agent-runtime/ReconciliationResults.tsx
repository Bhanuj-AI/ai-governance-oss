"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { CheckCircle2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import type { ReconcileResponse } from "@/types/agent-runtime";

// v2 excludes case-review findings. Changing the key prevents an old,
// pre-lifecycle result from being presented as a current reconciliation run.
export const RECONCILIATION_RESULT_STORAGE_KEY = "ai_governance.runtime_findings.reconciliation_result.v2";

function loadResult(): ReconcileResponse | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.sessionStorage.getItem(RECONCILIATION_RESULT_STORAGE_KEY);
    return value ? JSON.parse(value) as ReconcileResponse : null;
  } catch {
    return null;
  }
}

function ResultsContent({ onClose }: { onClose: () => void }) {
  const result = loadResult();
  if (!result) return <div className="p-6"><h1 className="text-lg font-semibold">No reconciliation result available</h1><p className="mt-2 text-sm text-muted-foreground">Run Reconcile from Operational Findings to inspect its evidence-window outcomes.</p><Button className="mt-5" onClick={onClose}>Back to findings</Button></div>;
  return <div className="flex max-h-[min(46rem,calc(100vh-3rem))] flex-col bg-background">
    <div className="flex items-start justify-between gap-4 border-b px-6 py-5"><div><p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">Runtime findings</p><h1 className="mt-1 text-xl font-semibold">Reconciliation results</h1><p className="mt-1 text-sm text-muted-foreground">{result.processed} open findings checked; {result.resolved} resolved from sustained recovery evidence.</p></div><Button type="button" variant="ghost" size="icon" onClick={onClose} aria-label="Close reconciliation results"><X className="h-4 w-4" /></Button></div>
    <div className="grid grid-cols-2 gap-px border-b bg-border sm:grid-cols-4">{Object.entries(result.outcomes).map(([outcome, count]) => <div className="bg-background px-4 py-3" key={outcome}><div className="text-xl font-semibold">{count}</div><div className="text-xs text-muted-foreground">{humanize(outcome)}</div></div>)}</div>
    <div className="min-h-0 flex-1 overflow-auto p-6">{result.findings.length === 0 ? <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">There were no open findings to reconcile.</p> : <div className="overflow-hidden rounded-md border"><table className="w-full text-sm"><thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-4 py-3">Finding</th><th className="px-4 py-3">Outcome</th><th className="px-4 py-3">Recovery evidence</th><th className="hidden px-4 py-3 lg:table-cell">Completed window</th></tr></thead><tbody className="divide-y">{result.findings.map((finding) => <tr key={finding.finding_id}><td className="px-4 py-3 font-mono text-xs">{finding.finding_id}</td><td className="px-4 py-3"><span className="font-medium">{humanize(finding.outcome)}</span>{finding.detail ? <p className="mt-1 max-w-sm text-xs text-muted-foreground">{finding.detail}</p> : null}</td><td className="px-4 py-3">{finding.consecutive_normal_windows} / {finding.required_normal_windows} healthy windows</td><td className="hidden px-4 py-3 text-xs text-muted-foreground lg:table-cell">{finding.window ? `${formatDate(finding.window.observed_start)} – ${formatDate(finding.window.observed_end)}` : "—"}</td></tr>)}</tbody></table></div>}</div>
    <div className="flex justify-end border-t px-6 py-4"><Button onClick={onClose}><CheckCircle2 className="h-4 w-4" />Done</Button></div>
  </div>;
}

export function ReconciliationResultsModal() {
  const router = useRouter();
  return <Dialog.Root open onOpenChange={(open) => { if (!open) router.back(); }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(78rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-lg border bg-background shadow-xl focus:outline-none"><Dialog.Title className="sr-only">Reconciliation results</Dialog.Title><Dialog.Description className="sr-only">Completed evidence-window outcomes for open runtime findings.</Dialog.Description><ResultsContent onClose={() => router.back()} /></Dialog.Content></Dialog.Portal></Dialog.Root>;
}

export function ReconciliationResultsPage() {
  const router = useRouter();
  return <main className="mx-auto max-w-6xl p-6"><div className="overflow-hidden rounded-lg border shadow-sm"><ResultsContent onClose={() => router.replace("/agents-runtime?view=findings")} /></div></main>;
}

function humanize(value: string) { return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString(); }
