"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { type ReactNode, useState } from "react";
import Link from "next/link";
import { Activity, AlertCircle, Sparkles, Zap } from "lucide-react";
import { StudioShell } from "@/components/layout/ConsoleShell";
import { AgentExecutionsPage } from "@/components/agent-runtime/AgentExecutionsPage";
import { AgentFindingsPage } from "@/components/agent-runtime/AgentFindingsPage";
import { CausalAuditPage } from "@/components/agent-runtime/CausalAuditPage";
import { Button } from "@/components/ui/button";
import { AIGovernanceApiError } from "@/lib/api/client";
import { getAgentRuntimeDemoStatus, seedAgentRuntimeDemo } from "@/lib/api/local-demo";

type TabId = "executions" | "findings" | "causal-audit";

export function AgentRuntimePage() {
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabId>(() => searchParams.get("causalAudit") || searchParams.get("view") === "policies" || searchParams.get("view") === "causal-audit" ? "causal-audit" : "executions");
  const [showDemoReadyBanner, setShowDemoReadyBanner] = useState(false);
  const queryClient = useQueryClient();
  const demoStatusQuery = useQuery({
    queryKey: ["agent-runtime-demo-status"],
    queryFn: getAgentRuntimeDemoStatus,
  });

  const seedMutation = useMutation({
    mutationFn: seedAgentRuntimeDemo,
    onSuccess: () => {
      setShowDemoReadyBanner(true);
      window.setTimeout(() => setShowDemoReadyBanner(false), 5_000);
      void queryClient.invalidateQueries({ queryKey: ["agent-executions"] });
      void queryClient.invalidateQueries({ queryKey: ["runtime-agents"] });
      void queryClient.invalidateQueries({ queryKey: ["runtime-findings"] });
      void queryClient.invalidateQueries({ queryKey: ["agent-runtime-demo-status"] });
    },
  });

  const isDemoReady = demoStatusQuery.data?.seeded === true;

  return (
    <StudioShell>
      <main className="h-[calc(100vh-4rem)] overflow-y-auto">
        <div className="studio-page flex flex-col gap-5 py-6">
          <section className="relative overflow-hidden rounded-xl border bg-card px-5 py-5 shadow-sm sm:px-6">
            <div className="absolute inset-y-0 left-0 w-1 bg-primary" aria-hidden="true" />
            <div className="flex flex-wrap items-start justify-between gap-5">
              <div className="flex max-w-2xl gap-3">
                <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Activity className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
                    Runtime Intelligence
                  </p>
                  <h1 className="mt-1 text-2xl font-semibold tracking-tight">Agents Runtime</h1>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    Inspect execution evidence, operational health, and explainable findings generated from observed runtime behaviour.
                  </p>
                </div>
              </div>
              <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto">
                <Button
                  type="button"
                  onClick={() => seedMutation.mutate()}
                  disabled={seedMutation.isPending || demoStatusQuery.data?.seeded === true}
                  className="shrink-0"
                >
                  {seedMutation.isPending ? <Sparkles className="h-4 w-4 animate-pulse" /> : <Zap className="h-4 w-4" />}
                  {seedMutation.isPending ? "Loading demo…" : demoStatusQuery.data?.seeded ? "Demo Data Loaded" : "Load Demo Data"}
                </Button>
                <Button asChild variant="outline" className="shrink-0">
                  <Link href="/settings?section=agents-runtime">Runtime Settings</Link>
                </Button>
              </div>
            </div>
          </section>

          {demoStatusQuery.isSuccess && (!isDemoReady || showDemoReadyBanner) && (
            <div className={`rounded-lg border px-4 py-3 text-sm ${demoStatusQuery.data.seeded ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200" : "border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-100"}`}>
              <p className="font-medium">{demoStatusQuery.data.seeded ? "Local demo data is ready." : "No local demo data is loaded."}</p>
              <p className="mt-0.5 opacity-90">{demoStatusQuery.data.seeded ? "The sample is available to explore. The load action is disabled to keep it idempotent." : "This is expected on a new local environment. Load the sample dataset to explore agents, executions, and findings."}</p>
            </div>
          )}

          <section className="rounded-xl border bg-card shadow-sm">
            <nav className="flex gap-1 border-b px-3" aria-label="Agents Runtime tabs">
              <TabButton active={activeTab === "executions"} onClick={() => setActiveTab("executions")}>Executions</TabButton>
              <TabButton active={activeTab === "findings"} onClick={() => setActiveTab("findings")}>Findings</TabButton>
              <TabButton active={activeTab === "causal-audit"} onClick={() => setActiveTab("causal-audit")}>Causal Audit</TabButton>
            </nav>
            <div className="p-4 sm:p-5">
              {activeTab === "executions" ? <AgentExecutionsPage demoDataPending={demoStatusQuery.data?.seeded === false} /> : activeTab === "findings" ? <AgentFindingsPage demoDataPending={demoStatusQuery.data?.seeded === false} /> : <CausalAuditPage demoDataPending={demoStatusQuery.data?.seeded === false} />}
            </div>
          </section>

          {seedMutation.isError && (
            <div role="alert" className="flex gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-medium">Demo data could not be loaded.</p>
                <p className="mt-0.5 text-destructive/90">{formatSeedError(seedMutation.error)}</p>
              </div>
            </div>
          )}
        </div>
      </main>
    </StudioShell>
  );
}

function TabButton({ active, children, onClick }: { active: boolean; children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`border-b-2 px-3 py-3 text-sm font-medium transition-colors ${
        active
          ? "border-primary text-primary"
          : "border-transparent text-muted-foreground hover:border-muted-foreground/30 hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

function formatSeedError(error: unknown) {
  if (error instanceof AIGovernanceApiError) {
    return error.message;
  }
  return error instanceof Error ? error.message : "Retry the request or check the local API logs.";
}
