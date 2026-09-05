"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, ChevronRight, CircleAlert, CircleHelp, Inbox } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { InterventionPolicyManagement } from "@/components/agent-runtime/InterventionPolicyManagement";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { listCausalAudits } from "@/lib/api/agent-runtime";
import type { CausalAuditClassification, CausalAuditDto } from "@/types/agent-runtime";

const classes: Array<CausalAuditClassification | ""> = ["", "EVIDENCE_ALIGNED", "EVIDENCE_IGNORED", "OVER_EXTENDED", "NO_TOOL_EVIDENCE"];

const classificationLabels: Record<CausalAuditClassification, string> = {
  NO_TOOL_EVIDENCE: "No Tool Evidence",
  EVIDENCE_IGNORED: "Evidence Ignored",
  OVER_EXTENDED: "Over-Extended",
  EVIDENCE_ALIGNED: "Evidence Aligned",
};

type HelpTopic = "overview" | "evidence-influence" | "intervention-policy" | CausalAuditClassification;

const classificationDescriptions: Record<CausalAuditClassification, string> = {
  EVIDENCE_ALIGNED: "Evidence materially influenced the outcome and tool usage remained appropriately bounded.",
  EVIDENCE_IGNORED: "Tool evidence was available but did not materially influence the evaluated outcome.",
  OVER_EXTENDED: "Useful evidence existed, but the agent continued unnecessary tool activity or exhausted its tool-call budget.",
  NO_TOOL_EVIDENCE: "No auditable tool evidence was available.",
};

function classificationLabel(value: CausalAuditClassification | null | undefined) {
  return value ? classificationLabels[value] : "Pending";
}

function auditClassificationLabel(audit: CausalAuditDto) {
  if (audit.classification) return classificationLabel(audit.classification);
  if (audit.status === "FAILED") return "Not Classified";
  if (audit.status === "CANCELLED") return "Cancelled";
  return "In progress";
}

function auditStatusLabel(audit: CausalAuditDto) {
  if (audit.status === "FAILED") return "Needs review";
  if (audit.status === "CANCELLED") return "Cancelled";
  if (audit.status === "SUCCEEDED") return "Completed";
  return audit.status === "QUEUED" ? "Queued" : "Running";
}

export function CausalAuditPage({ demoDataPending = false }: { demoDataPending?: boolean }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [view, setView] = useState<"audits" | "policies">(() => searchParams.get("view") === "policies" || Boolean(searchParams.get("policyExecution")) ? "policies" : "audits");
  const [classification, setClassification] = useState<CausalAuditClassification | "">("");
  const [helpOpen, setHelpOpen] = useState(false);
  const [helpTopic, setHelpTopic] = useState<HelpTopic>("overview");
  const selectedExecutionId = searchParams.get("policyExecution") ?? undefined;
  const legacyAuditId = searchParams.get("causalAudit");
  const query = useQuery({ queryKey: ["causal-audits", classification], queryFn: () => listCausalAudits({ classification: classification || undefined }), enabled: !demoDataPending });
  const items = query.data?.items ?? [];
  const summary = (value: CausalAuditClassification) => items.filter((item) => item.classification === value).length;
  const completedCount = items.filter((item) => item.status === "SUCCEEDED").length;
  const reviewCount = items.filter((item) => item.status === "FAILED" || item.status === "CANCELLED").length;
  const openHelp = (topic: HelpTopic) => { setHelpTopic(topic); setHelpOpen(true); };
  useEffect(() => {
    if (legacyAuditId) router.replace(`/agents-runtime/causal-audits/${encodeURIComponent(legacyAuditId)}`);
  }, [legacyAuditId, router]);
  return <div className="flex flex-col gap-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><Activity className="h-4 w-4 text-primary" /><h2 className="font-semibold">Causal Audit</h2></div><p className="mt-1 text-sm text-muted-foreground">Determine whether agent outcomes genuinely depend on evidence returned by tools.</p></div><div className="flex items-center gap-2"><Button variant="ghost" size="sm" onClick={() => openHelp("overview")} aria-label="Open Causal Audit help"><CircleHelp className="h-4 w-4" />Help</Button><select aria-label="Causal audit classification" className="h-9 rounded-md border bg-background px-3 text-sm" value={classification} onChange={(event) => setClassification(event.target.value as CausalAuditClassification | "")}>{classes.map((value) => <option value={value} key={value || "all"}>{value ? classificationLabel(value) : "All classifications"}</option>)}</select></div></div>
    <nav className="flex gap-1 border-b" aria-label="Causal Audit sections"><LocalTab active={view === "audits"} onClick={() => setView("audits")}>Audits</LocalTab><LocalTab active={view === "policies"} onClick={() => setView("policies")}>Intervention Policies</LocalTab></nav>
    {view === "audits" && <><div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5"><Metric label="Total audits" value={items.length} detail={`${completedCount} completed${reviewCount ? ` · ${reviewCount} needs review` : ""}`} tone="total" /><Metric label="Evidence Aligned" value={summary("EVIDENCE_ALIGNED")} detail="Evidence used appropriately" tone="aligned" /><Metric label="Evidence Ignored" value={summary("EVIDENCE_IGNORED")} detail="Evidence had low influence" tone="ignored" /><Metric label="Over-Extended" value={summary("OVER_EXTENDED")} detail="Calls continued after saturation" tone="extended" /><Metric label="No Tool Evidence" value={summary("NO_TOOL_EVIDENCE")} detail="No auditable evidence found" tone="absent" /></div>
    {demoDataPending && <Empty />}
    {!demoDataPending && query.isLoading && <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">Loading causal audits…</div>}
    {!demoDataPending && query.isError && <div role="alert" className="flex gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"><CircleAlert className="h-4 w-4" />{query.error instanceof Error ? query.error.message : "Causal audits could not be loaded."}</div>}
    {!demoDataPending && query.isSuccess && items.length === 0 && <Empty />}
    {!demoDataPending && query.isSuccess && items.length > 0 &&
      <>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-4 py-3">Execution</th>
            <th className="px-4 py-3">Review</th>
            <th className="px-4 py-3">
              <span className="inline-flex items-center gap-1">Evidence influence <InlineHelpButton topic="evidence-influence" onOpenHelp={openHelp} /></span>
            </th>
            <th className="px-4 py-3">Agent</th>
            <th className="px-4 py-3">Classification</th>
            <th className="px-4 py-3">Tool calls</th>
            <th className="px-4 py-3">Audit state</th>
          </tr>
          </thead>
          <tbody className="divide-y">{
            items.map((audit) =>
              <tr key={audit.audit_id} className="hover:bg-muted/30">
                <td className="px-4 py-3 font-mono text-xs">{audit.execution_id}</td>
                <td className="px-4 py-3">
                  <Link
                    href={`/agents-runtime/causal-audits/${encodeURIComponent(audit.audit_id)}`}
                    className={`inline-flex items-center gap-0.5 rounded-md border px-2 py-1 text-xs font-semibold transition-colors ${audit.status === "SUCCEEDED" ? "border-cyan-200 bg-cyan-300 text-slate-950 hover:bg-cyan-200" : "border-amber-200 bg-amber-300 text-slate-950 hover:bg-amber-200"}`}
                  >
                      {audit.status === "SUCCEEDED" ? "Explain" : "Review"} <ChevronRight className="h-3.5 w-3.5" />
                  </Link>
                </td>
                <td className="px-4 py-3">{audit.status === "SUCCEEDED" && audit.tool_call_results.length ? `${Math.max(...audit.tool_call_results.map((result) => result.influence_score)).toFixed(2)}` : "—"}</td>
                <td className="px-4 py-3">{audit.agent_id}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-1">
                    <Badge variant="outline" className={auditClassificationBadgeClassName(audit)}>{auditClassificationLabel(audit)}</Badge>{audit.classification ? <InlineHelpButton topic={audit.classification} onOpenHelp={openHelp} /> : null}
                  </span>
                </td>
                <td className="px-4 py-3">{audit.status === "FAILED" || audit.status === "CANCELLED" ? "—" : audit.tool_call_results.length}</td>
                <td className="px-4 py-3">
                  <div className={audit.status === "FAILED" ? "font-medium text-destructive" : "font-medium"}>{auditStatusLabel(audit)}</div>{audit.failure_code ? <div className="mt-0.5 max-w-40 truncate text-xs text-muted-foreground" title={audit.failure_reason ?? audit.failure_code}>{audit.failure_code}</div> : null}
                </td>
              </tr>)}</tbody>
        </table>
      </div>
      </>
    }</>}
    {view === "policies" && <InterventionPolicyManagement onOpenHelp={() => openHelp("intervention-policy")} selectedExecutionId={selectedExecutionId} />}
    <CausalAuditHelpDrawer open={helpOpen} onOpenChange={setHelpOpen} topic={helpTopic} onTopicChange={setHelpTopic} />
  </div>;
}

function InlineHelpButton({ topic, onOpenHelp }: { topic: Exclude<HelpTopic, "overview">; onOpenHelp: (topic: HelpTopic) => void }) {
  const label = topic === "evidence-influence" ? "Explain evidence influence" : topic === "intervention-policy" ? "Explain intervention policies" : `Explain ${classificationLabel(topic)}`;
  return <button type="button" className="rounded-sm text-muted-foreground hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring" aria-label={label} onClick={() => onOpenHelp(topic)}><CircleHelp className="h-3.5 w-3.5" /></button>;
}

function CausalAuditHelpDrawer({ open, onOpenChange, topic, onTopicChange }: { open: boolean; onOpenChange: (open: boolean) => void; topic: HelpTopic; onTopicChange: (topic: HelpTopic) => void }) {
  const focusedTitle = topic === "overview" ? null : topic === "evidence-influence" ? "Evidence Influence" : topic === "intervention-policy" ? "Intervention Policies" : classificationLabel(topic);

  return <Sheet open={open} onOpenChange={onOpenChange}>
    <SheetContent className="overflow-y-auto sm:max-w-lg">
      <SheetHeader className="pr-8">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">Agents Runtime</p>
        <SheetTitle>Causal Audit Help</SheetTitle>
      </SheetHeader>
      <div className="mt-6 space-y-5 text-sm">
        {focusedTitle ? <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm"><span className="text-muted-foreground">Showing help for </span><span className="font-medium">{focusedTitle}</span></div> : null}
        <HelpSection title="What is Causal Audit?">
          Causal Audit tests whether evidence returned by an agent&apos;s tools materially influenced its evaluated outcome. It compares the observed outcome with controlled counterfactual evidence.
        </HelpSection>
        <HelpSection title="How it works">
          <p className="font-medium text-foreground">Observed Execution → Tool Evidence → Controlled Intervention → Re-evaluation → Evidence Influence → Classification</p>
        </HelpSection>
        <HelpSection title="Intervention Policies" highlighted={topic === "intervention-policy"}>
          Defines which controlled alternative evidence may be used during Causal Audit. An operator validates and explicitly activates an immutable policy version before it can be reused.
          <dl className="mt-3 space-y-2 text-xs"><div><dt className="font-medium text-foreground">NULLIFY</dt><dd>Tests the execution without usable evidence from the selected tool call.</dd></div><div><dt className="font-medium text-foreground">REPLACE</dt><dd>Substitutes another known-valid evidence instance.</dd></div><div><dt className="font-medium text-foreground">PERTURB</dt><dd>Makes a bounded, schema-valid modification to selected evidence.</dd></div></dl>
        </HelpSection>
        <HelpSection title="Classifications" highlighted={topic !== "overview" && topic !== "evidence-influence" && topic !== "intervention-policy"}>
          <dl className="space-y-3">
            {classes.filter((value): value is CausalAuditClassification => Boolean(value)).map((classification) => <div key={classification}><button type="button" className="font-medium text-foreground hover:text-primary hover:underline" onClick={() => onTopicChange(classification)}>{classificationLabel(classification)}</button><dd className="mt-0.5 leading-6 text-muted-foreground">{classificationDescriptions[classification]}</dd></div>)}
          </dl>
        </HelpSection>
        <HelpSection title="Understanding Evidence Influence" highlighted={topic === "evidence-influence"}>
          <p>Evidence Influence measures how much the evaluated outcome changes when observed tool evidence is replaced by controlled counterfactual evidence. Higher influence indicates greater outcome dependence on that evidence.</p>
          <p className="mt-3 rounded-md bg-muted/50 p-3 text-xs leading-5 text-muted-foreground"><span className="font-medium text-foreground">Low influence is not automatically a defect.</span> The evidence may genuinely have been redundant.</p>
        </HelpSection>
        <HelpSection title="Important limitations">
          Causal Audit measures outcome sensitivity under controlled interventions. It does not establish universal causation or prove that an agent&apos;s internal reasoning followed a particular path.
        </HelpSection>
      </div>
    </SheetContent>
  </Sheet>;
}

function HelpSection({ title, highlighted = false, children }: { title: string; highlighted?: boolean; children: ReactNode }) {
  return <section className={highlighted ? "rounded-lg border border-primary/20 bg-primary/5 p-4" : "rounded-lg border p-4"}><h3 className="font-medium">{title}</h3><div className="mt-2 leading-6 text-muted-foreground">{children}</div></section>;
}

function Metric({ label, value, detail, tone }: { label: string; value: number; detail: string; tone: "total" | "aligned" | "ignored" | "extended" | "absent" }) {
  const toneClasses = {
    total: {
      card: "border-border bg-card hover:bg-muted/20",
      label: "border-border bg-muted text-foreground",
    },
    aligned: {
      card: "border-emerald-400/60 bg-card hover:bg-emerald-500/5",
      label: "border-emerald-200 bg-emerald-300 text-slate-950",
    },
    ignored: {
      card: "border-amber-400/60 bg-card hover:bg-amber-500/5",
      label: "border-amber-200 bg-amber-300 text-slate-950",
    },
    extended: {
      card: "border-orange-400/60 bg-card hover:bg-orange-500/5",
      label: "border-orange-200 bg-orange-300 text-slate-950",
    },
    absent: {
      card: "border-sky-400/60 bg-card hover:bg-sky-500/5",
      label: "border-sky-200 bg-sky-300 text-slate-950",
    },
  }[tone];
  return <div className={`min-h-24 rounded-lg border px-4 py-3 transition-colors ${toneClasses.card}`}><Badge variant="outline" className={toneClasses.label}>{label}</Badge><div className="mt-3 text-2xl font-semibold tabular-nums">{value}</div><div className="mt-1 text-xs text-muted-foreground">{detail}</div></div>;
}
function LocalTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) { return <button type="button" onClick={onClick} className={`border-b-2 px-3 py-2 text-sm font-medium ${active ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>{children}</button>; }
function auditClassificationBadgeClassName(audit: CausalAuditDto) {
  if (audit.classification === "EVIDENCE_ALIGNED") return "border-emerald-200 bg-emerald-300 text-slate-950";
  if (audit.classification === "EVIDENCE_IGNORED") return "border-amber-200 bg-amber-300 text-slate-950";
  if (audit.classification === "OVER_EXTENDED") return "border-orange-200 bg-orange-300 text-slate-950";
  if (audit.classification === "NO_TOOL_EVIDENCE") return "border-sky-200 bg-sky-300 text-slate-950";
  if (audit.status === "FAILED") return "border-rose-200 bg-rose-300 text-slate-950";
  if (audit.status === "CANCELLED") return "border-slate-300 bg-slate-300 text-slate-950";
  return "border-violet-200 bg-violet-300 text-slate-950";
}

export function CausalAuditDetail({ audit }: { audit: CausalAuditDto }) {
  const postSaturationResults = audit.tool_call_results.filter((result) => result.post_saturation);
  const saturationResult = audit.tool_call_results.find((result) => result.useful);

  const maxInfluence = audit.tool_call_results.length ? Math.max(...audit.tool_call_results.map((result) => result.influence_score)) : null;
  const firstMaterial = audit.tool_call_results.find((result) => result.useful) ?? audit.tool_call_results[0];
  const isTerminalFailure = audit.status === "FAILED" || audit.status === "CANCELLED";

  return <section className="overflow-hidden rounded-lg border bg-card"><div className="border-b px-5 py-4"><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">Classification Reasoning</h3><Badge variant="outline" className={auditClassificationBadgeClassName(audit)}>{auditClassificationLabel(audit)}</Badge></div><p className="mt-1 max-w-4xl text-sm leading-6 text-muted-foreground">{String(audit.diagnostics.classification_reason ?? (isTerminalFailure ? "This audit did not complete, so no causal classification was produced." : "The audit is still running; no classification has been produced."))}</p>{isTerminalFailure ? <div role="alert" className="mt-3 rounded-md border border-rose-200 bg-rose-300 px-3 py-2 text-sm text-slate-950"><span className="font-semibold">{audit.failure_code ?? "Audit did not complete"}</span>{audit.failure_reason ? ` — ${audit.failure_reason}` : null}</div> : null}{!isTerminalFailure && firstMaterial && maxInfluence !== null ? <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><OutcomeFact label="Evidence influence" value={formatInfluence(maxInfluence)} detail="Largest observed change" tone="influence" /><OutcomeFact label="Observed outcome" value={firstMaterial.baseline_score.value.toFixed(3)} detail="Before intervention" tone="observed" /><OutcomeFact label="Counterfactual" value={firstMaterial.counterfactual_score.value.toFixed(3)} detail="After controlled evidence" tone="counterfactual" /><OutcomeFact label="Tool-use outcome" value={postSaturationResults.length ? "Over-extended" : "Bounded"} detail={postSaturationResults.length ? `${postSaturationResults.length} post-saturation call${postSaturationResults.length === 1 ? "" : "s"}` : "No post-saturation calls"} tone={postSaturationResults.length ? "extended" : "bounded"} /></div> : null}{postSaturationResults.length > 0 ? <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-amber-400/50 bg-card px-3 py-2 text-sm"><Badge variant="outline" className="border-amber-200 bg-amber-300 text-slate-950">Saturation reached</Badge><span>Call #{(saturationResult?.position ?? 0) + 1}{saturationResult ? ` · ${saturationResult.tool_name} · Influence ${formatInfluence(saturationResult.influence_score)}` : null}</span><span className="text-muted-foreground">· Calls {postSaturationResults.map((result) => `#${result.position + 1}`).join("–")} occurred after saturation</span></div> : null}</div>{audit.tool_call_results.length === 0 ? <p className="px-5 py-6 text-sm text-muted-foreground">{isTerminalFailure ? "No causal result was produced because the audit did not complete." : "No tool-call evidence was audited for this execution."}</p> : <div className="divide-y">{audit.tool_call_results.map((result) => <section key={result.tool_call_id} className="p-5"><div className="flex flex-wrap items-center gap-2"><h4 className="font-semibold">{result.tool_name}</h4><Badge variant="outline" className={toolCallBadgeClassName(result)}>{result.post_saturation ? "Post-saturation" : result.useful ? "Material influence" : result.harmful ? "Harmful influence" : "No material influence"}</Badge></div><div className="mt-4 grid gap-3 rounded-lg border bg-muted/10 p-3 text-sm sm:grid-cols-[0.65fr_1fr_1.65fr]"><Fact label="Tool call" value={`#${result.position + 1}`} /><Fact label="Intervention" value={`${result.intervention_strategy} · ${result.counterfactual_count} sample${result.counterfactual_count === 1 ? "" : "s"}`} /><Fact label="Score chain" value={<ScoreChain result={result} />} /></div><div className="mt-3 grid gap-3 lg:grid-cols-2"><EvidenceDetails result={result} /><ControlledReplayDetails result={result} /></div></section>)}</div>}</section>;
}
function OutcomeFact({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: "influence" | "observed" | "counterfactual" | "bounded" | "extended" }) {
  const toneClasses = {
    influence: { card: "border-cyan-400/50 bg-card", label: "border-cyan-200 bg-cyan-300 text-slate-950" },
    observed: { card: "border-sky-400/50 bg-card", label: "border-sky-200 bg-sky-300 text-slate-950" },
    counterfactual: { card: "border-violet-400/50 bg-card", label: "border-violet-200 bg-violet-300 text-slate-950" },
    bounded: { card: "border-emerald-400/50 bg-card", label: "border-emerald-200 bg-emerald-300 text-slate-950" },
    extended: { card: "border-orange-400/50 bg-card", label: "border-orange-200 bg-orange-300 text-slate-950" },
  }[tone];
  return <div className={`rounded-md border px-3 py-2.5 ${toneClasses.card}`}><Badge variant="outline" className={toneClasses.label}>{label}</Badge><div className="mt-2 font-semibold">{value}</div><div className="mt-1 text-xs text-muted-foreground">{detail}</div></div>;
}
function toolCallBadgeClassName(result: CausalAuditDto["tool_call_results"][number]) {
  if (result.post_saturation) return "border-orange-200 bg-orange-300 text-slate-950";
  if (result.useful) return "border-emerald-200 bg-emerald-300 text-slate-950";
  if (result.harmful) return "border-rose-200 bg-rose-300 text-slate-950";
  return "border-slate-300 bg-slate-300 text-slate-950";
}
function EvidenceDetails({ result }: { result: CausalAuditDto["tool_call_results"][number] }) {
  return <details className="rounded-lg border bg-card p-3 text-xs text-muted-foreground"><summary className="cursor-pointer font-medium text-foreground">Evidence details</summary><dl className="mt-3 grid gap-3 leading-5"><div><dt className="font-medium text-foreground">Evidence references</dt><dd className="mt-0.5 break-all font-mono">{result.evidence_references.join(", ") || "None"}</dd></div><div className="grid gap-3 sm:grid-cols-2"><div><dt className="font-medium text-foreground">Strategy version</dt><dd className="mt-0.5">{result.intervention_strategy_version}</dd></div><div><dt className="font-medium text-foreground">Seed</dt><dd className="mt-0.5">{result.intervention_seed === null ? "Not used" : result.intervention_seed}</dd></div></div></dl></details>;
}
function ControlledReplayDetails({ result }: { result: CausalAuditDto["tool_call_results"][number] }) {
  return <details className="rounded-lg border bg-card p-3 text-xs text-muted-foreground"><summary className="cursor-pointer font-medium text-foreground">Controlled replays <span className="text-muted-foreground">({result.counterfactual_replay_ids.length})</span></summary>{result.counterfactual_lineage.length > 0 ? <div className="mt-3 space-y-2">{result.counterfactual_lineage.map((lineage) => <div key={lineage.replay_id} className="rounded-md border bg-muted/10 p-2.5"><dl className="grid gap-2 sm:grid-cols-2"><div><dt className="font-medium text-foreground">Controlled replay</dt><dd className="mt-0.5 break-all font-mono">{lineage.replay_id}</dd></div><div><dt className="font-medium text-foreground">Replay execution</dt><dd className="mt-0.5 break-all font-mono">{lineage.replay_execution_id}</dd></div><div><dt className="font-medium text-foreground">Governed policy</dt><dd className="mt-0.5">{lineage.policy_id} v{lineage.policy_version}</dd></div><div><dt className="font-medium text-foreground">Evaluator score</dt><dd className="mt-0.5 font-semibold text-foreground">{lineage.evaluator_score.value.toFixed(3)}</dd></div></dl></div>)}</div> : <p className="mt-3">Replay lineage is unavailable.</p>}</details>;
}
function Fact({ label, value }: { label: string; value: ReactNode }) { return <div><div className="text-xs text-muted-foreground">{label}</div><div className="mt-0.5 break-words">{value}</div></div>; }
function ScoreChain({ result }: { result: CausalAuditDto["tool_call_results"][number] }) { return <><span className="font-medium">Original {result.baseline_score.value.toFixed(3)}</span> → Counterfactual {result.counterfactual_score.value.toFixed(3)} <span className="text-muted-foreground">|</span> <span className="font-semibold">Influence {formatInfluence(result.influence_score)}</span></>; }
function formatInfluence(value: number) { return `${value >= 0 ? "+" : ""}${value.toFixed(3)}`; }
function Empty() { return <div className="flex min-h-56 flex-col items-center justify-center rounded-lg border border-dashed bg-muted/20 text-center"><Inbox className="h-5 w-5 text-muted-foreground" /><p className="mt-2 text-sm font-medium">No causal audits yet</p><p className="mt-1 max-w-md text-sm text-muted-foreground">Eligible executions can be queued for an isolated counterfactual audit. An unaudited execution is not a causal conclusion.</p></div>; }
