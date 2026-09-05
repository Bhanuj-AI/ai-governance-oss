"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { AlertCircle, CircleHelp, Radar, RefreshCw, ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import {
  listRuntimeFindings,
  triggerDetection,
  reconcileFindings,
  reviewRuntimeFinding,
} from "@/lib/api/agent-runtime";
import { listSettings } from "@/lib/api/settings";
import { AIGovernanceApiError } from "@/lib/api/client";
import type { FindingSeverity, FindingStatus, RuntimeFinding } from "@/types/agent-runtime";
import type { PlatformSetting } from "@/types/settings";
import { RECONCILIATION_RESULT_STORAGE_KEY } from "@/components/agent-runtime/ReconciliationResults";

const SEVERITY_OPTIONS: { value: FindingSeverity | ""; label: string }[] = [
  { value: "", label: "All severities" },
  { value: "CRITICAL", label: "Critical" },
  { value: "HIGH", label: "High" },
  { value: "MEDIUM", label: "Medium" },
  { value: "LOW", label: "Low" },
  { value: "INFO", label: "Info" },
];

const STATUS_OPTIONS: { value: FindingStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "OPEN", label: "Open" },
  { value: "ACKNOWLEDGED", label: "Acknowledged" },
  { value: "CLOSED", label: "Closed" },
  { value: "RESOLVED", label: "Resolved" },
];

export function AgentFindingsPage({ demoDataPending = false }: { demoDataPending?: boolean }) {
  const router = useRouter();
  const [severityFilter, setSeverityFilter] = useState<FindingSeverity | "">("");
  const [statusFilter, setStatusFilter] = useState<FindingStatus | "">("OPEN");
  const [limit] = useState(50);

  const findingsQuery = useQuery({
    queryKey: ["runtime-findings", severityFilter, statusFilter, limit],
    queryFn: () =>
      listRuntimeFindings({
        severity: severityFilter || undefined,
        status: statusFilter || undefined,
        limit,
      }),
    enabled: !demoDataPending,
  });

  const thresholdsQuery = useQuery({
    queryKey: ["settings", "Agents Runtime", "SYSTEM"],
    queryFn: () => listSettings("Agents Runtime", "SYSTEM"),
    enabled: !demoDataPending,
  });

  const detectionMutation = useMutation({
    mutationFn: triggerDetection,
    onSuccess: () => {
      findingsQuery.refetch();
    },
  });

  const reconcileMutation = useMutation({
    mutationFn: reconcileFindings,
    onSuccess: (result) => {
      findingsQuery.refetch();
      window.sessionStorage.setItem(RECONCILIATION_RESULT_STORAGE_KEY, JSON.stringify(result));
      router.push("/agents-runtime/findings/reconciliation");
    },
  });

  const reviewMutation = useMutation({
    mutationFn: ({ findingId, action }: { findingId: string; action: "ACKNOWLEDGE" | "CLOSE" }) =>
      reviewRuntimeFinding(findingId, action),
    onSuccess: () => findingsQuery.refetch(),
  });

  const openCount = findingsQuery.data?.items.filter(
    (f) => f.status === "OPEN",
  ).length ?? 0;
  const requiredNormalWindows = requiredRecoveryWindows(thresholdsQuery.data);

  return <div className="flex flex-col gap-4">
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
        <div className="flex items-center gap-2"><Radar className="h-4 w-4 text-primary" /><h2 className="font-semibold">Operational Findings</h2></div>
        <p className="mt-1 text-sm text-muted-foreground">Deterministic operational and causal conclusions with bounded evidence, not LLM-generated alerts.</p>
        </div>
        <div className="flex gap-2">
        <FindingsHelpPanel />
        <Button size="sm" className="border border-cyan-200 bg-cyan-300 text-slate-950 hover:bg-cyan-200" onClick={() => detectionMutation.mutate()} disabled={demoDataPending || detectionMutation.isPending}>
          <RefreshCw className={`h-3.5 w-3.5 ${detectionMutation.isPending ? "animate-spin" : ""}`} />Detect
        </Button>
        <Button size="sm" className="border border-emerald-200 bg-emerald-300 text-slate-950 hover:bg-emerald-200" onClick={() => reconcileMutation.mutate()} disabled={demoDataPending || reconcileMutation.isPending}>
          <RefreshCw className={`h-3.5 w-3.5 ${reconcileMutation.isPending ? "animate-spin" : ""}`} />Reconcile Operational
        </Button>
        </div>
      </div>
      <DetectorThresholdSummary settings={thresholdsQuery.data} isLoading={thresholdsQuery.isLoading} />
    </div>

    <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-muted/30 p-3">
      <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
        Severity
        <select aria-label="Filter findings by severity"
            value={severityFilter}
            disabled={demoDataPending}
            onChange={(e) => setSeverityFilter(e.target.value as FindingSeverity | "")}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {SEVERITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
      </label>
      <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
        Lifecycle
        <select aria-label="Filter findings by lifecycle status"
            value={statusFilter}
            disabled={demoDataPending}
            onChange={(e) => setStatusFilter(e.target.value as FindingStatus | "")}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
      </label>
    </div>

    {findingsQuery.isSuccess && <div className="grid gap-3 sm:grid-cols-2"><SummaryCard label="Open findings" value={openCount} tone="alert" /><SummaryCard label="Findings in view" value={findingsQuery.data.items.length} tone="neutral" /></div>}

      {demoDataPending && (
        <div className="flex min-h-60 flex-col items-center justify-center rounded-lg border border-dashed bg-muted/20 px-6 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-background text-muted-foreground shadow-sm"><ShieldAlert className="h-5 w-5" /></div>
          <span className="mt-3 text-sm font-semibold text-foreground">No findings to display yet</span>
          <span className="mt-1 max-w-md text-sm text-muted-foreground">Load the local demo dataset to inspect example findings, or send execution evidence from a connected runtime.</span>
        </div>
      )}

      {!demoDataPending && findingsQuery.isLoading && (
        <div className="flex min-h-56 items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground">
          Loading runtime findings…
        </div>
      )}

      {!demoDataPending && findingsQuery.isError && (
        <div role="alert" className="flex gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          {findingsQuery.error instanceof Error
            ? findingsQuery.error.message
            : "Failed to load findings."}
        </div>
      )}

      {!demoDataPending && findingsQuery.isSuccess && findingsQuery.data.items.length === 0 && (
        <div className="flex min-h-60 flex-col items-center justify-center rounded-lg border border-dashed bg-muted/20 px-6 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-background text-muted-foreground shadow-sm"><ShieldAlert className="h-5 w-5" /></div>
          <span className="mt-3 text-sm font-semibold text-foreground">No findings match this view</span>
          <span className="mt-1 max-w-sm text-sm text-muted-foreground">Run detection when execution evidence is available, or load demo data to inspect example findings.</span>
        </div>
      )}

      {!demoDataPending && findingsQuery.isSuccess && findingsQuery.data.items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Severity</th>
                <th className="px-4 py-3 text-left font-medium">Finding</th>
                <th className="px-4 py-3 text-left font-medium">Subject</th>
                <th className="px-4 py-3 text-left font-medium">Evidence / Change</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {findingsQuery.data.items.map((finding) => (
                <tr key={finding.findingId} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <SeverityBadge severity={finding.severity} />
                  </td>
                  <td className="px-4 py-3"><div className="font-medium">{formatFindingType(finding.findingType)}</div><div className="mt-0.5 font-mono text-xs text-muted-foreground">{finding.detectorId}</div>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    <span className="text-muted-foreground">{finding.subjectType}:</span>{" "}
                    {finding.subjectId}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {formatEvidenceChange(finding)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={finding.status} />
                    {finding.lifecycle === "CASE_REVIEW" ? (
                      <CaseReviewActions finding={finding} onReview={(action) => reviewMutation.mutate({ findingId: finding.findingId, action })} pending={reviewMutation.isPending} />
                    ) : <FindingRecoveryState finding={finding} requiredNormalWindows={requiredNormalWindows} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detectionMutation.isError && (
        <InlineError message={formatError(detectionMutation.error)} />
      )}
      {reconcileMutation.isError && (
        <InlineError message={formatError(reconcileMutation.error)} />
      )}
      {reviewMutation.isError && <InlineError message={formatError(reviewMutation.error)} />}
  </div>;
}

function DetectorThresholdSummary({ settings, isLoading }: { settings?: PlatformSetting[]; isLoading: boolean }) {
  if (isLoading) {
    return <p className="text-xs text-muted-foreground">Loading configured detector thresholds…</p>;
  }
  if (!settings) return null;

  const value = (key: string) => settings.find((setting) => setting.key === key)?.effective_value;
  const percentage = (key: string) => formatPercentage(value(key));
  const multiple = (key: string) => formatMultiple(value(key));
  const thresholdItems = [
    {
      label: "Tool Failures",
      value: `${percentage("runtime_findings.tool_failure_rate.absolute_threshold")} and ${multiple("runtime_findings.tool_failure_rate.relative_threshold")}`,
      className: "border-cyan-200 bg-cyan-300 text-slate-950",
    },
    {
      label: "Agent Failures",
      value: `${percentage("runtime_findings.agent_execution_failure_rate.absolute_threshold")} and ${multiple("runtime_findings.agent_execution_failure_rate.relative_threshold")}`,
      className: "border-blue-200 bg-blue-300 text-slate-950",
    },
    {
      label: "Latency",
      value: multiple("runtime_findings.execution_latency_regression.relative_threshold"),
      className: "border-violet-200 bg-violet-300 text-slate-950",
    },
    {
      label: "Evaluation Failures",
      value: `${percentage("runtime_findings.evaluation_failure_rate.absolute_threshold")} and ${multiple("runtime_findings.evaluation_failure_rate.relative_threshold")}`,
      className: "border-amber-200 bg-amber-300 text-slate-950",
    },
    {
      label: "Policy Fenials",
      value: `${percentage("runtime_findings.policy_denial_rate.absolute_threshold")} and ${multiple("runtime_findings.policy_denial_rate.relative_threshold")}`,
      className: "border-orange-200 bg-orange-300 text-slate-950",
    },
    {
      label: "Repeated Errors",
      value: `≥${formatNumber(value("runtime_findings.repeated_runtime_error.absolute_threshold"))} occurrences`,
      className: "border-rose-200 bg-rose-300 text-slate-950",
    },
  ];

  return <div className="rounded-lg border bg-muted/20 px-3 py-2.5" aria-label="Configured detector thresholds">
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
      <span className="shrink-0 font-medium text-muted-foreground">Thresholds</span>
      <div className="flex flex-1 flex-wrap items-center gap-2">
        {thresholdItems.map((item) => <span key={item.label} className={`rounded-md border px-2 py-1 ${item.className}`}><span className="font-medium">{item.label}</span> {item.value}</span>)}
      </div>
    </div>
  </div>;
}

function FindingRecoveryState({ finding, requiredNormalWindows }: { finding: RuntimeFinding; requiredNormalWindows: number }) {
  if (finding.status !== "OPEN" || !finding.lastReconciliation) return null;

  const { outcome, detail } = finding.lastReconciliation;
  if (outcome === "HEALTHY_AWAITING") {
    return <div className="mt-1 text-xs text-muted-foreground" title="Latest reconciliation found a healthy finalized window. Additional consecutive healthy windows are required before resolution.">
      Recovery {finding.consecutiveNormalWindows} / {requiredNormalWindows} finalized window{requiredNormalWindows === 1 ? "" : "s"}
    </div>;
  }
  if (outcome === "INSUFFICIENT_DATA") {
    return <div className="mt-1 text-xs text-muted-foreground" title={`Latest reconciliation: insufficient finalized evidence to establish a healthy recovery window.${detail ? ` ${detail}` : ""}`}>
      Awaiting Recovery Evidence
    </div>;
  }
  if (outcome === "CONDITION_PRESENT") {
    return <div className="mt-1 text-xs text-muted-foreground" title="Latest reconciliation found that the condition is still present.">Condition Still Present</div>;
  }
  if (outcome === "PROGRESS_RESET") {
    return <div className="mt-1 text-xs text-muted-foreground" title="Latest reconciliation found a recurrence, so healthy recovery progress was reset.">Recovery Progress Reset</div>;
  }
  if (outcome === "UNSUPPORTED") {
    return <div className="mt-1 text-xs text-muted-foreground" title={detail || "This detector cannot be reconciled safely."}>Recovery Evidence Unsupported</div>;
  }
  if (outcome === "FAILED") {
    return <div className="mt-1 text-xs text-muted-foreground" title={detail || "The latest reconciliation attempt failed."}>Recovery Check Failed</div>;
  }
  if (outcome === "ALREADY_RECONCILED") {
    return <div className="mt-1 text-xs text-muted-foreground" title="This finalized recovery window was already checked. A later finalized window is required for new recovery progress.">Awaiting next finalized recovery window</div>;
  }
  return null;
}

function requiredRecoveryWindows(settings?: PlatformSetting[]): number {
  const value = Number(settings?.find((setting) => setting.key === "runtime_findings.auto_resolution.consecutive_normal_windows")?.effective_value);
  return Number.isInteger(value) && value > 0 ? value : 2;
}

function formatPercentage(value: unknown): string {
  const number = Number(value);
  return Number.isFinite(number) ? `≥${number * 100}%` : "—";
}

function formatMultiple(value: unknown): string {
  const number = Number(value);
  return Number.isFinite(number) ? `≥${number}× baseline` : "—";
}

function formatNumber(value: unknown): string {
  const number = Number(value);
  return Number.isFinite(number) ? String(number) : "—";
}

function SummaryCard({ label, value, tone }: { label: string; value: number; tone: "alert" | "neutral" }) {
  return <Card className="shadow-none"><CardContent className="flex items-center justify-between p-4"><span className="text-sm text-muted-foreground">{label}</span><span className={`text-2xl font-semibold ${tone === "alert" && value > 0 ? "text-destructive" : "text-foreground"}`}>{value}</span></CardContent></Card>;
}

function FindingsHelpPanel() {
  return <Sheet>
    <SheetTrigger asChild>
      <Button variant="ghost" size="sm" aria-label="Explain runtime findings"><CircleHelp className="h-4 w-4" />How this works</Button>
    </SheetTrigger>
    <SheetContent className="overflow-y-auto sm:max-w-lg">
      <SheetHeader className="pr-8">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">Runtime intelligence</p>
        <SheetTitle>How operational findings work</SheetTitle>
        <p className="text-sm leading-6 text-muted-foreground">Findings are deterministic conclusions built from execution evidence. They are not generated by an LLM.</p>
      </SheetHeader>
      <div className="mt-7 space-y-6 text-sm">
        <HelpStep number="1" title="Collect execution evidence">Runtime events supply the measured evidence: execution outcomes, durations, tool calls, evaluations, policy decisions, and errors.</HelpStep>
        <HelpStep number="2" title="Detect operational conditions"><strong>Detect</strong> evaluates the configured detectors across the current evidence and creates or refreshes findings when a threshold is exceeded. It compares a configured historical baseline with a current observation window.</HelpStep>
        <HelpStep number="3" title="Keep operational findings honest"><strong>Reconcile Operational</strong> rechecks only open operational findings against a completed, detector-configured window. Re-running it in the same window is idempotent; it cannot add recovery progress twice.</HelpStep>
        <HelpStep number="4" title="Resolve sustained recovery">An operational finding resolves only after the configured number of consecutive normal windows (default: two). This prevents a single healthy period from making an intermittent problem disappear.</HelpStep>
        <HelpStep number="5" title="Review causal evidence">A Causal Audit replays one observed execution in isolation with an approved evidence change. Its finding shows evidence influence or the affected tool call, not a time-series baseline comparison. Acknowledge and close it as a reviewed historical case; reconciliation never changes it.</HelpStep>
        <div className="rounded-lg border bg-muted/40 p-4"><p className="font-medium">When to use each action</p><dl className="mt-3 space-y-2 text-muted-foreground"><div><dt className="font-medium text-foreground">Detect</dt><dd>After new execution evidence arrives, or when you want to evaluate the latest behaviour.</dd></div><div><dt className="font-medium text-foreground">Reconcile operational</dt><dd>After remediation, to verify whether an operational finding has genuinely recovered.</dd></div><div><dt className="font-medium text-foreground">Acknowledge / close</dt><dd>For a causal finding, record that a person reviewed the completed execution. This never changes the historical audit result.</dd></div></dl></div>
        <p className="rounded-lg border border-primary/20 bg-primary/5 p-4 text-xs leading-5 text-muted-foreground">Thresholds, baseline windows, severity bands, and the recovery-window count are configurable in <span className="font-medium text-foreground">Settings → Agents Runtime</span>.</p>
      </div>
    </SheetContent>
  </Sheet>;
}

function HelpStep({ number, title, children }: { number: string; title: string; children: ReactNode }) {
  return <div className="flex gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{number}</span><div><h3 className="font-medium">{title}</h3><p className="mt-1 leading-6 text-muted-foreground">{children}</p></div></div>;
}

function SeverityBadge({ severity }: { severity: FindingSeverity }) {
  const color = severity === "CRITICAL"
    ? "border-rose-200 bg-rose-300 text-slate-950"
    : severity === "HIGH"
      ? "border-orange-200 bg-orange-300 text-slate-950"
    : severity === "MEDIUM"
        ? "border-amber-200 bg-amber-300 text-slate-950"
        : severity === "LOW"
          ? "border-sky-200 bg-sky-300 text-slate-950"
          : "border-blue-200 bg-blue-300 text-slate-950";

  return (
    <Badge variant="outline" className={`font-semibold ${color}`}>
      {severity}
    </Badge>
  );
}

function StatusBadge({ status }: { status: FindingStatus }) {
  const color = status === "OPEN"
    ? "border-orange-200 bg-orange-300 text-slate-950"
    : status === "ACKNOWLEDGED"
      ? "border-sky-200 bg-sky-300 text-slate-950"
      : "border-emerald-200 bg-emerald-300 text-slate-950";

  return (
    <Badge variant="outline" className={`font-semibold ${color}`}>
      {status}
    </Badge>
  );
}

function CaseReviewActions({ finding, onReview, pending }: { finding: RuntimeFinding; onReview: (action: "ACKNOWLEDGE" | "CLOSE") => void; pending: boolean }) {
  if (finding.status === "CLOSED") return <div className="mt-1 text-xs text-muted-foreground">Case closed after review</div>;
  if (finding.status === "ACKNOWLEDGED") return <div className="mt-1 flex items-center gap-2"><span className="text-xs text-muted-foreground">Manual case review</span><Button size="sm" className="h-7 border border-emerald-200 bg-emerald-300 px-2 text-xs text-slate-950 hover:bg-emerald-200" disabled={pending} onClick={() => onReview("CLOSE")}>Close</Button></div>;
  return <div className="mt-1 flex items-center gap-2"><span className="text-xs text-muted-foreground">Manual case review</span><Button size="sm" className="h-7 border border-sky-200 bg-sky-300 px-2 text-xs text-slate-950 hover:bg-sky-200" disabled={pending} onClick={() => onReview("ACKNOWLEDGE")}>Acknowledge</Button></div>;
}

function formatEvidenceChange(finding: RuntimeFinding) {
  if (finding.detectorId === "causal_audit") {
    const influence = finding.observedMetrics.find(
      (metric) => metric.name === "max_evidence_influence",
    )?.value;
    const toolCall = finding.evidenceReferences.find(
      (reference) => reference.kind === "tool_call_id",
    )?.value;
    const toolCount = finding.observedMetrics[0]?.sampleSize;

    if (finding.findingType === "REDUNDANT_TOOL_CALL" && toolCall) {
      return `Tool call: ${shortIdentifier(toolCall)}`;
    }
    if (typeof influence === "number" && Number.isFinite(influence)) {
      const detail = finding.findingType === "OVER_EXTENDED" && toolCount
        ? ` · ${toolCount} tool calls`
        : "";
      return `Influence: ${formatValue(influence)}${detail}`;
    }
    return toolCall ? `Tool call: ${shortIdentifier(toolCall)}` : "Causal evidence recorded";
  }

  const baseline = finding.baselineMetrics[0];
  const observed = finding.observedMetrics[0];
  if (!baseline || !observed) return "—";
  return `${formatValue(baseline.value)} → ${formatValue(observed.value)}`;
}

function shortIdentifier(value: string) {
  return value.length > 18 ? `…${value.slice(-12)}` : value;
}

function formatValue(value: number) {
  if (value < 0.01 && value > 0) return value.toExponential(2);
  if (value >= 1000) return value.toLocaleString();
  return value.toFixed(2);
}

function formatFindingType(value: string) {
  return value.split("_").map((part) => part.charAt(0) + part.slice(1).toLowerCase()).join(" ");
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
      <AlertCircle className="h-4 w-4 shrink-0" />
      {message}
    </div>
  );
}

function formatError(error: unknown) {
  if (error instanceof AIGovernanceApiError) {
    return `${error.code}: ${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unexpected error.";
}
