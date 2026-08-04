"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  Clock,
  Database,
  FileText,
  GitBranch,
  ListChecks,
  Network,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { DecisionFlowGraph } from "@/components/decisions/DecisionFlowGraph";
import { DecisionStatusBadge } from "@/components/decisions/DecisionStatusBadge";
import {
  GovernedEventFlow,
  type GovernedFlowStep,
} from "@/components/governance/GovernedEventFlow";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getDecisionDetail,
  getDecisionEvidence,
  getDecisionExplanation,
  getDecisionLineage,
} from "@/lib/api/decisions";
import { KavachApiError } from "@/lib/api/client";
import {
  evidenceGraphToFlow,
  lineageToFlow,
} from "@/lib/decisions/flow";
import type {
  DecisionAuditRecord,
  DecisionDetail,
  DecisionEvidence,
  DecisionExplanation,
  DecisionLineage,
  GovernanceDecision,
  MissingEvidence,
  PolicyOutcome,
  ReasoningEvidenceSummary,
} from "@/types/decision";

export function DecisionDetailPage({ decisionId }: { decisionId: string }) {
  const detailQuery = useQuery({
    queryKey: ["decision-detail", decisionId],
    queryFn: () => getDecisionDetail(decisionId),
  });
  const evidenceQuery = useQuery({
    queryKey: ["decision-evidence", decisionId],
    queryFn: () => getDecisionEvidence(decisionId),
  });
  const explanationQuery = useQuery({
    queryKey: ["decision-explanation", decisionId],
    queryFn: () => getDecisionExplanation(decisionId),
  });
  const lineageQuery = useQuery({
    queryKey: ["decision-lineage", decisionId, 2],
    queryFn: () => getDecisionLineage(decisionId, 2),
  });

  const notFound =
    detailQuery.error instanceof KavachApiError &&
    detailQuery.error.status === 404;

  if (notFound) {
    return (
      <DecisionPageFrame decisionId={decisionId}>
        <EmptyState
          icon={<AlertCircle className="h-5 w-5" />}
          title="Decision not found"
          description="The API returned 404 for this decision identifier."
        />
      </DecisionPageFrame>
    );
  }

  return (
    <DecisionPageFrame
      decisionId={decisionId}
      decision={detailQuery.data?.decision}
    >
      {detailQuery.isLoading ? (
        <LoadingState label="Loading decision detail..." />
      ) : detailQuery.isError ? (
        <ErrorState error={detailQuery.error} />
      ) : detailQuery.data ? (
        <DecisionContent
          detail={detailQuery.data}
          evidence={sectionState(evidenceQuery)}
          explanation={sectionState(explanationQuery)}
          lineage={sectionState(lineageQuery)}
        />
      ) : (
        <EmptyState
          icon={<ShieldCheck className="h-5 w-5" />}
          title="No decision data"
          description="The detail response did not include a decision."
        />
      )}
    </DecisionPageFrame>
  );
}

function DecisionPageFrame({
  decisionId,
  decision,
  children,
}: {
  decisionId: string;
  decision?: GovernanceDecision;
  children: React.ReactNode;
}) {
  return (
    <div className="h-[calc(100vh-3.5rem)] overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1480px] flex-col gap-5 px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <Link
              href="/decisions"
              className="mb-3 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" />
              Decision index
            </Link>
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <h1 className="max-w-full truncate text-2xl font-semibold tracking-normal">
                Governance Decision
              </h1>
              {decision ? <DecisionStatusBadge value={decision.status} /> : null}
            </div>
            <div className="mt-1 max-w-[920px] truncate font-mono text-xs text-muted-foreground">
              {decisionId}
            </div>
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

function DecisionContent({
  detail,
  evidence,
  explanation,
  lineage,
}: {
  detail: DecisionDetail;
  evidence: SectionState<DecisionEvidence>;
  explanation: SectionState<DecisionExplanation>;
  lineage: SectionState<DecisionLineage>;
}) {
  return (
    <>
      <DecisionLifecycle
        decision={detail.decision}
        summary={detail.evidenceSummary}
        policies={detail.policyOutcomes}
      />
      <PolicyEvaluation policies={detail.policyOutcomes} />
      <ExplanationSection state={explanation} />
      <EvidenceGraphSection state={evidence} />
      <LineageSection state={lineage} />
      <AuditSection auditRecords={detail.auditRecords} />

    </>
  );
}

function DecisionLifecycle({
  decision,
  summary,
  policies,
}: {
  decision: GovernanceDecision;
  summary: ReasoningEvidenceSummary;
  policies: PolicyOutcome[];
}) {
  const metrics = Object.entries(summary.metricScores);
  const tone = decisionOutcomeTone(decision.status);
  const steps: GovernedFlowStep[] = [
    {
      id: "evidence",
      label: "collect decision evidence",
      detail: `${decision.evidence.length} evidence reference${decision.evidence.length === 1 ? "" : "s"} and ${metrics.length} metric score${metrics.length === 1 ? "" : "s"} were considered.`,
      tone: "info",
    },
    {
      id: "policy",
      label: "evaluate policy",
      detail: `${policies.length} governed policy outcome${policies.length === 1 ? "" : "s"} were evaluated against the target.`,
      tone: "progress",
    },
    {
      id: "decision",
      label: "record governance decision",
      detail: "The policy result is committed as a durable, explainable decision.",
      tone,
    },
    {
      id: "audit",
      label: "retain audit evidence",
      detail: summary.latestAuditStatus
        ? `Audit evidence is recorded with status ${summary.latestAuditStatus}.`
        : "Audit metadata remains available with the decision record.",
      tone,
    },
  ];

  return (
    <GovernedEventFlow
      stream="Decision / policy evaluation"
      steps={steps}
      outcomeLabel="Governed outcome"
      outcome={`${decision.status} · ${decision.confidence} CONFIDENCE`}
      outcomeDetail={decision.reason}
      outcomeTone={tone}
      activeStep={3}
      footer={
        <div className="space-y-3">
          {metrics.length ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Metric scores</span>
              {metrics.map(([metricId, score]) => (
                <Badge key={metricId} variant="outline" className="border-primary/25 bg-primary/5 text-primary">
                  <span className="max-w-[180px] truncate">{metricId}</span>&nbsp;{score.toFixed(3)}
                </Badge>
              ))}
            </div>
          ) : <MutedLine>No metric scores were included in the detail model.</MutedLine>}
          <details>
            <summary className="cursor-pointer text-sm font-medium">Decision Metadata</summary>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Target type" value={decision.target.targetType} />
              <Field label="Target ID" value={decision.target.targetId} mono />
              <Field label="Producer" value={decision.provenance.producerId} />
              <Field label="Created" value={formatDate(decision.provenance.createdAt)} />
              <Field label="Correlation" value={decision.provenance.correlationId ?? "Not provided"} mono />
              <Field label="Request" value={decision.provenance.requestId ?? "Not provided"} mono />
              <Field label="Latest job" value={summary.latestJobStatus ?? "Unavailable"} />
              <Field label="Latest audit" value={summary.latestAuditStatus ?? "Unavailable"} />
            </div>
          </details>
        </div>
      }
    />
  );
}

function PolicyEvaluation({ policies }: { policies: PolicyOutcome[] }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-primary" />
          Policy Evaluation
        </CardTitle>
      </CardHeader>
      <CardContent>
        {policies.length ? (
          <div className="space-y-3">
            {policies.map((policy) => (
              <div
                key={`${policy.policyId}:${policy.policyVersion}`}
                className="rounded-lg border bg-muted/10 p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link
                      href={`/policies/${encodeURIComponent(policy.policyId)}/versions/${encodeURIComponent(policy.policyVersion)}`}
                      className="block truncate text-sm font-semibold underline-offset-4 hover:text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      title={`Open ${policy.policyId} version ${policy.policyVersion}`}
                    >
                      {policy.policyId}
                    </Link>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Version {policy.policyVersion}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <DecisionStatusBadge value={policy.effect} />
                    <DecisionStatusBadge
                      value={policy.matched ? "MATCHED" : "NOT MATCHED"}
                    />
                  </div>
                </div>
                {policy.matchedRuleId ? (
                  <div className="mt-3 inline-flex max-w-full rounded-md bg-background px-2.5 py-1.5 font-mono text-xs text-muted-foreground">
                    Rule: {policy.matchedRuleId}
                  </div>
                ) : null}
                <p className="mt-3 max-w-4xl text-sm leading-6">{policy.reason}</p>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<ListChecks className="h-5 w-5" />}
            title="No policy outcomes"
            description="The decision detail model did not include policy outcomes."
          />
        )}
      </CardContent>
    </Card>
  );
}

function EvidenceGraphSection({
  state,
}: {
  state: SectionState<DecisionEvidence>;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Network className="h-4 w-4 text-primary" />
          Evidence Graph
        </CardTitle>
      </CardHeader>
      <CardContent>
        <SectionSwitch state={state} emptyTitle="No evidence graph">
          {(evidence) => (
            <EvidenceGraphContent evidence={evidence} />
          )}
        </SectionSwitch>
      </CardContent>
    </Card>
  );
}

function EvidenceGraphContent({ evidence }: { evidence: DecisionEvidence }) {
  const flow = useMemo(
    () => evidenceGraphToFlow(evidence.evidenceGraph),
    [evidence.evidenceGraph],
  );

  if (!evidence.evidenceGraph.nodes.length) {
    return (
      <EmptyState
        icon={<Network className="h-5 w-5" />}
        title="No evidence nodes"
        description="The backend returned an empty evidence graph."
      />
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
      <div className="h-[440px] min-w-0 overflow-hidden rounded-md border bg-background">
        <DecisionFlowGraph nodes={flow.nodes} edges={flow.edges} />
      </div>
      <EvidenceSidePanel
        references={evidence.evidenceReferences.length}
        missing={evidence.evidenceGraph.missing}
        nodes={evidence.evidenceGraph.nodes.length}
        edges={evidence.evidenceGraph.edges.length}
      />
    </div>
  );
}

function EvidenceSidePanel({
  references,
  missing,
  nodes,
  edges,
}: {
  references: number;
  missing: MissingEvidence[];
  nodes: number;
  edges: number;
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <MiniStat label="Refs" value={String(references)} />
        <MiniStat label="Nodes" value={String(nodes)} />
        <MiniStat label="Edges" value={String(edges)} />
      </div>
      <div className="rounded-md border bg-background p-3">
        <div className="text-xs font-medium uppercase text-muted-foreground">
          Missing Evidence
        </div>
        {missing.length ? (
          <div className="mt-3 space-y-2">
            {missing.map((item) => (
              <div key={`${item.evidenceType}:${item.reason}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">
                    {item.evidenceType}
                  </span>
                  <DecisionStatusBadge value={item.severity} />
                </div>
                <div className="mt-1 text-xs leading-5 text-muted-foreground">
                  {item.reason}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <MutedLine>No missing evidence was reported.</MutedLine>
        )}
      </div>
    </div>
  );
}

function ExplanationSection({
  state,
}: {
  state: SectionState<DecisionExplanation>;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-primary" />
          Reasoning Explanation
        </CardTitle>
      </CardHeader>
      <CardContent>
        <SectionSwitch state={state} emptyTitle="No explanation">
          {(explanation) => (
            <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
              <div className="rounded-md border bg-background p-3 text-sm leading-6">
                {explanation.summary || "No explanation summary returned."}
              </div>
              <div className="space-y-3">
                {explanation.reasons.length ? (
                  explanation.reasons.map((reason, index) => (
                    <div
                      key={`${reason}:${index}`}
                      className="grid grid-cols-[34px_1fr] gap-3"
                    >
                      <div className="flex h-7 w-7 items-center justify-center rounded-full border bg-card text-xs font-semibold">
                        {index + 1}
                      </div>
                      <div className="rounded-md border bg-background p-3 text-sm leading-6">
                        {reason}
                      </div>
                    </div>
                  ))
                ) : (
                  <MutedLine>No reasoning timeline entries returned.</MutedLine>
                )}
              </div>
            </div>
          )}
        </SectionSwitch>
      </CardContent>
    </Card>
  );
}

function LineageSection({ state }: { state: SectionState<DecisionLineage> }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-primary" />
          Decision Lineage
        </CardTitle>
      </CardHeader>
      <CardContent>
        <details>
          <summary className="cursor-pointer text-sm font-medium">
            Show full lineage graph
          </summary>
          <p className="mt-1 text-sm text-muted-foreground">
            Use this broader graph for investigation. The evidence graph above is the focused view for this decision.
          </p>
          <div className="mt-4">
            <SectionSwitch state={state} emptyTitle="No lineage graph">
              {(lineage) => <LineageContent lineage={lineage} />}
            </SectionSwitch>
          </div>
        </details>
      </CardContent>
    </Card>
  );
}

function LineageContent({ lineage }: { lineage: DecisionLineage }) {
  const flow = useMemo(() => lineageToFlow(lineage), [lineage]);

  if (!lineage.subgraph.nodes.length) {
    return (
      <EmptyState
        icon={<GitBranch className="h-5 w-5" />}
        title="No lineage nodes"
        description="The backend returned an empty lineage subgraph."
      />
    );
  }

  return (
    <div className="h-[420px] overflow-hidden rounded-md border bg-background">
      <DecisionFlowGraph nodes={flow.nodes} edges={flow.edges} />
    </div>
  );
}

function AuditSection({
  auditRecords,
}: {
  auditRecords: DecisionAuditRecord[];
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Database className="h-4 w-4 text-primary" />
          Audit Metadata
        </CardTitle>
      </CardHeader>
      <CardContent>
        {auditRecords.length ? (
          <div className="space-y-3">
            {auditRecords.map((record) => (
              <div
                key={record.auditId}
                className="grid gap-3 rounded-md border bg-background p-3 lg:grid-cols-[170px_1fr_260px]"
              >
                <div>
                  <DecisionStatusBadge value={record.action} />
                  <div className="mt-2 font-mono text-xs text-muted-foreground">
                    {record.auditId}
                  </div>
                </div>
                <div className="text-sm leading-6">{record.reason}</div>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5" />
                    {formatDate(record.createdAt)}
                  </div>
                  <div className="truncate">Producer: {record.producerId}</div>
                  <div className="truncate">
                    Request: {record.requestId ?? "Not provided"}
                  </div>
                  <div className="truncate">
                    Correlation: {record.correlationId ?? "Not provided"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<Database className="h-5 w-5" />}
            title="No audit records"
            description="The decision detail model did not include audit records."
          />
        )}
      </CardContent>
    </Card>
  );
}

function SectionSwitch<T>({
  state,
  emptyTitle,
  children,
}: {
  state: SectionState<T>;
  emptyTitle: string;
  children: (data: T) => React.ReactNode;
}) {
  if (state.status === "loading") {
    return <LoadingState label="Loading section..." />;
  }
  if (state.status === "error") {
    return <ErrorState error={state.error} compact />;
  }
  if (state.status === "empty") {
    return (
      <EmptyState
        icon={<AlertCircle className="h-5 w-5" />}
        title={emptyTitle}
        description="The API returned no data for this section."
      />
    );
  }
  return <>{children(state.data)}</>;
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0 rounded-md border bg-background px-3 py-2">
      <div className="text-xs font-medium uppercase text-muted-foreground">
        {label}
      </div>
      <div
        className={`mt-1 truncate text-sm ${mono ? "font-mono" : "font-medium"}`}
      >
        {value}
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border bg-background px-3 py-2">
      <div className="text-[11px] font-medium uppercase text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 truncate text-sm font-semibold">{value}</div>
    </div>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex min-h-[180px] items-center justify-center rounded-md border bg-card text-sm text-muted-foreground">
      {label}
    </div>
  );
}

function ErrorState({
  error,
  compact = false,
}: {
  error: Error;
  compact?: boolean;
}) {
  return (
    <div
      className={`flex items-start gap-2 rounded-md border border-destructive/30 bg-card px-3 py-2 text-sm text-destructive ${compact ? "" : "min-h-[180px]"}`}
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{errorMessage(error)}</span>
    </div>
  );
}

function EmptyState({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex min-h-[160px] flex-col items-center justify-center rounded-md border bg-card px-4 py-6 text-center">
      <div className="text-muted-foreground">{icon}</div>
      <div className="mt-2 text-sm font-semibold">{title}</div>
      <div className="mt-1 max-w-[520px] text-sm text-muted-foreground">
        {description}
      </div>
    </div>
  );
}

function MutedLine({ children }: { children: React.ReactNode }) {
  return <div className="text-sm text-muted-foreground">{children}</div>;
}

type SectionState<T> =
  | { status: "loading" }
  | { status: "error"; error: Error }
  | { status: "empty" }
  | { status: "ready"; data: T };

function sectionState<T>(query: {
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  data: T | undefined;
}): SectionState<T> {
  if (query.isLoading) {
    return { status: "loading" };
  }
  if (query.isError) {
    return { status: "error", error: query.error ?? new Error("Unknown error") };
  }
  if (query.data === undefined || query.data === null) {
    return { status: "empty" };
  }
  return { status: "ready", data: query.data };
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function errorMessage(error: Error) {
  if (error instanceof KavachApiError) {
    return `${error.code}: ${error.message}`;
  }
  return error.message;
}

type SemanticTone = "info" | "success" | "warning" | "danger" | "muted";

function semanticTone(value: string): SemanticTone {
  const normalized = value.toLowerCase();
  if (["approved", "approve", "allow", "allowed", "created", "active", "high", "matched", "pass", "passed", "succeeded", "success", "completed"].includes(normalized)) return "success";
  if (["medium", "pending", "proposed", "review", "recommend", "warn", "warning", "quarantine", "investigate"].includes(normalized)) return "warning";
  if (["blocked", "block", "critical", "deny", "denied", "failed", "failure", "low", "rejected", "reject"].includes(normalized)) return "danger";
  if (["unavailable", "not matched", "unknown"].includes(normalized)) return "muted";
  return "info";
}


function decisionOutcomeTone(value: string): Exclude<SemanticTone, "muted"> {
  const tone = semanticTone(value);
  return tone === "muted" ? "info" : tone;
}
