"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, AlertCircle, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { CausalAuditDetail } from "@/components/agent-runtime/CausalAuditPage";
import { getCausalAudit } from "@/lib/api/agent-runtime";

export function CausalAuditDetailPage({ auditId }: { auditId: string }) {
  const query = useQuery({
    queryKey: ["causal-audits", "detail", auditId],
    queryFn: () => getCausalAudit(auditId),
  });

  return <main className="h-[calc(100vh-4rem)] overflow-y-auto">
    <div className="studio-page mx-auto flex max-w-7xl flex-col gap-5 py-6">
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link href="/agents-runtime" className="hover:text-foreground hover:underline">Agents Runtime</Link>
        <span aria-hidden="true">/</span>
        <Link href="/agents-runtime?view=causal-audit" className="hover:text-foreground hover:underline">Causal Audit</Link>
        <span aria-hidden="true">/</span>
        <span className="font-mono text-xs text-foreground">{shortId(auditId)}</span>
      </nav>
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-xl border bg-card px-5 py-5 shadow-sm sm:px-6">
        <div className="flex max-w-3xl gap-3">
          <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-cyan-300 text-slate-950"><Activity className="h-5 w-5" /></div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Causal Audit</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">Evidence influence</h1>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">Review the finalized classification, controlled evidence, and replay lineage for this audit.</p>
          </div>
        </div>
        {query.data ? <Badge variant="outline" className={statusBadgeClassName(query.data.status)}>{humanize(query.data.status)}</Badge> : null}
      </div>
      <Link href="/agents-runtime?view=causal-audit" className="inline-flex w-fit items-center gap-1 rounded-md border border-sky-200 bg-sky-300 px-3 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-sky-200"><ArrowLeft className="h-4 w-4" />Back to Causal Audit</Link>
      {query.isLoading ? <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">Loading causal audit evidence…</div> : null}
      {query.isError ? <div role="alert" className="flex gap-3 rounded-lg border border-rose-200 bg-rose-300 p-4 text-sm text-slate-950"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />{query.error instanceof Error ? query.error.message : "This causal audit could not be loaded."}</div> : null}
      {query.data ? <CausalAuditDetail audit={query.data} /> : null}
    </div>
  </main>;
}

function statusBadgeClassName(status: string) {
  if (status === "SUCCEEDED") return "border-transparent bg-[#32d74b] text-[#1f2328]";
  if (status === "FAILED") return "border-rose-200 bg-rose-300 text-slate-950";
  if (status === "CANCELLED") return "border-slate-300 bg-slate-300 text-slate-950";
  return "border-amber-200 bg-amber-300 text-slate-950";
}

function shortId(value: string) { return value.length > 16 ? `${value.slice(0, 10)}…${value.slice(-4)}` : value; }
function humanize(value: string) { return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase()); }
