"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  Circle,
  ExternalLink,
  Loader2,
  PartyPopper,
  Play,
  Route,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useTenantContext } from "@/components/tenancy/TenantContextProvider";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { JourneyStage } from "@/components/ui/journey";
import { getDashboardSummary } from "@/lib/api/dashboard";
import { listExperiments } from "@/lib/api/experiments";
import { seedLocalDemoData } from "@/lib/api/local-demo";
import { ONBOARDING_STARTUP_KEY } from "@/lib/onboarding";
import { listReplays } from "@/lib/api/replays";
import { listDatasetAssets, listModelAssets, listPromptAssets } from "@/lib/api/registries";
import { listProjects } from "@/lib/api/tenancy";

const JOURNEY_PROGRESS_KEY = "ai_governance.onboarding.journey-baselines";
const JOURNEY_MANUAL_STEPS_KEY = "ai_governance.onboarding.manually-reviewed-steps";
const ACTIVE_JOURNEY_KEY = "ai_governance.onboarding.active-journey";

type Snapshot = {
  projects: number;
  assets: number;
  observedAssets: number;
  experiments: number;
  evaluations: number;
  decisions: number;
  replays: number;
  graphNodes: number;
  apiReady: boolean;
  databaseReady: boolean;
  neo4jReady: boolean;
};

type JourneyStep = {
  id: string;
  title: string;
  explanation: string;
  why: string[];
  href: string;
  action: string;
  docsHref: string;
  isSystem?: boolean;
  complete: (current: Snapshot, baseline: Snapshot) => boolean;
};

type Journey = {
  id: string;
  title: string;
  estimate: string;
  description: string;
  unlocks: string[];
  steps: JourneyStep[];
};

const docs = "https://ai_governance.bhanuj.app/docs";

const JOURNEYS: Journey[] = [
  {
    id: "getting-started",
    title: "Getting Started",
    estimate: "15 min",
    description: "Build one new governed workflow in your selected project.",
    unlocks: ["Asset Registry", "Runtime Observation", "Evaluation", "Governance", "Replay"],
    steps: [
      { id: "api", title: "API Running", explanation: "Studio can reach the AI Governance Control Plane control-plane API.", why: ["Studio uses the API to read and record governance state.", "A healthy API confirms your local control plane is ready."], href: "/", action: "View platform health", docsHref: `${docs}/rest-apis`, isSystem: true, complete: current => current.apiReady },
      { id: "database", title: "Postgres Connected", explanation: "The control-plane persistence surface is responding.", why: ["Governance records must persist beyond a browser session.", "The database keeps evidence, decisions, and audit history durable."], href: "/", action: "View platform health", docsHref: `${docs}/persistence`, isSystem: true, complete: current => current.databaseReady },
      { id: "neo4j", title: "Neo4j Connected", explanation: "The graph store is ready to project and explore lineage.", why: ["AI Governance Control Plane connects evidence instead of leaving it in isolated records.", "The graph makes source, evaluation, decision, and replay lineage explorable."], href: "/graph", action: "Open Ontology", docsHref: `${docs}/ontology-synchronization`, isSystem: true, complete: current => current.neo4jReady },
      { id: "project", title: "Create Project", explanation: "Projects keep governed work scoped to the right team and workload.", why: ["Projects isolate governance, assets, and replay by workload.", "Without projects, everything mixes together."], href: "/organization/projects?onboarding=create", action: "Create Project", docsHref: `${docs}/rbac`, complete: (current, baseline) => current.projects > baseline.projects },
      { id: "asset", title: "Register Asset", explanation: "Register an evaluation dataset—a versioned asset your experiment can use as durable evidence.", why: ["An evaluation needs a stable input set to be repeatable.", "Versioned datasets make later comparisons defensible."], href: "/assets/datasets?onboarding=register", action: "Register Dataset", docsHref: `${docs}/assets`, complete: (current, baseline) => current.assets > baseline.assets },
      { id: "observe", title: "Observe Runtime", explanation: "Run an instrumented request from your application so AI Governance Control Plane can capture prompt and model evidence without taking over authoring or serving.", why: ["Runtime evidence captures what actually served a result.", "That evidence links a later evaluation or replay to the exact prompt and model."], href: "/assets?onboarding=observe", action: "Open Observation Setup", docsHref: `${docs}/tutorials/observed-assets`, complete: (current, baseline) => current.observedAssets > baseline.observedAssets },
      { id: "experiment", title: "Create Experiment", explanation: "Experiments hold candidate configurations and their evaluation runs. Create one, add a candidate, then produce evidence to compare and review.", why: ["Experiments compare candidate configurations under the same conditions.", "Without a shared experiment, scores cannot be compared fairly."], href: "/experiments?onboarding=create", action: "Create Experiment", docsHref: `${docs}/evaluation-engine`, complete: (current, baseline) => current.experiments > baseline.experiments && current.evaluations > baseline.evaluations },
      { id: "decision", title: "Review Decision", explanation: "After governance produces a new outcome, open the decision index to inspect its policy result and evidence.", why: ["A decision turns policy checks into a reviewable outcome.", "Its evidence explains why AI Governance Control Plane approved, blocked, or flagged the work."], href: "/decisions", action: "Open Decision Index", docsHref: `${docs}/tutorials/reviewing-governance-decisions`, complete: (current, baseline) => current.decisions > baseline.decisions },
      { id: "replay", title: "Create Replay", explanation: "Replays reproduce a governed execution from frozen historical evidence.", why: ["Replays test a past execution without changing the original record.", "They reveal whether a change introduces measurable drift."], href: "/replays/new", action: "Create Replay", docsHref: `${docs}/replay-management`, complete: (current, baseline) => current.replays > baseline.replays },
    ],
  },
  {
    id: "governance-fundamentals",
    title: "Governance Fundamentals",
    estimate: "45 min",
    description: "Turn evaluation evidence into an explainable governance outcome.",
    unlocks: ["Policies", "Decision Graph", "Ontology"],
    steps: [
      { id: "experiment", title: "Create Experiment", explanation: "Create an experiment, add a candidate, then run fresh evaluation evidence in the selected project.", why: ["Governance needs comparable evidence before it can assess a change.", "An experiment creates that evidence for candidate configurations."], href: "/experiments?onboarding=create", action: "Create Experiment", docsHref: `${docs}/evaluation-engine`, complete: (current, baseline) => current.experiments > baseline.experiments && current.evaluations > baseline.evaluations },
      { id: "decision", title: "Inspect New Governance Decision", explanation: "After governance produces a new outcome, inspect its policy result and supporting evidence in the decision index.", why: ["Governance is useful only when its outcome can be understood.", "The decision records the policy result and the evidence behind it."], href: "/decisions", action: "Open Decision Index", docsHref: `${docs}/tutorials/reviewing-governance-decisions`, complete: (current, baseline) => current.decisions > baseline.decisions },
      { id: "ontology", title: "Explore Decision Lineage", explanation: "Follow the governed relationships into the ontology graph.", why: ["Lineage shows how evidence became a governance decision.", "It helps reviewers trace a conclusion without reconstructing the workflow manually."], href: "/graph", action: "Open Ontology", docsHref: `${docs}/governance-ontology`, complete: (current, baseline) => current.graphNodes > baseline.graphNodes },
    ],
  },
  {
    id: "replay-engineering",
    title: "Replay Engineering",
    estimate: "45 min",
    description: "Prepare, inspect, and run a replay using frozen governed evidence.",
    unlocks: ["Replay Lineage", "Comparison", "Drift Analysis"],
    steps: [
      { id: "source", title: "Inspect Replayable Rvidence", explanation: "In the replay creator, find a governed execution with the evidence needed to reproduce it.", why: ["A replay must start from frozen historical evidence.", "That preserves the original execution while allowing a new comparison."], href: "/replays/new", action: "Find Source Execution", docsHref: `${docs}/replay-management`, complete: (current, baseline) => current.replays > baseline.replays },
      { id: "prepare", title: "Prepare New Replay", explanation: "Create a durable replay request from the selected source execution.", why: ["Replay configuration is frozen before work is queued.", "That makes the reproduction repeatable and auditable."], href: "/replays/new", action: "Create Replay", docsHref: `${docs}/tutorials/governed-replay`, complete: (current, baseline) => current.replays > baseline.replays },
      { id: "lineage", title: "Inspect Replay Lineage", explanation: "Use the graph to understand the source, replay, and governed result relationship.", why: ["Replay lineage connects the source, new execution, and comparison result.", "It makes drift evidence explainable in one view."], href: "/graph", action: "Open Ontology", docsHref: `${docs}/replay-management`, complete: (current, baseline) => current.graphNodes > baseline.graphNodes },
    ],
  },
];

function readProgress(): Record<string, Snapshot> {
  if (typeof window === "undefined") return {};
  try {
    const parsed = JSON.parse(window.localStorage.getItem(JOURNEY_PROGRESS_KEY) ?? "{}");
    return parsed && typeof parsed === "object" ? parsed as Record<string, Snapshot> : {};
  } catch {
    return {};
  }
}

function readManualSteps(): Record<string, string[]> {
  if (typeof window === "undefined") return {};
  try {
    const parsed = JSON.parse(window.localStorage.getItem(JOURNEY_MANUAL_STEPS_KEY) ?? "{}");
    return parsed && typeof parsed === "object" ? parsed as Record<string, string[]> : {};
  } catch {
    return {};
  }
}

export function OnboardingJourney({ onOpenDashboard }: { onOpenDashboard?: () => void }) {
  const tenant = useTenantContext();
  const [progress, setProgress] = useState(readProgress);
  const [manualSteps, setManualSteps] = useState(readManualSteps);
  const [activeJourneyId, setActiveJourneyId] = useState(() =>
    typeof window === "undefined" ? "getting-started" : window.localStorage.getItem(ACTIVE_JOURNEY_KEY) ?? "getting-started",
  );
  const [hideOnStartup, setHideOnStartup] = useState(() =>
    typeof window !== "undefined" && window.localStorage.getItem(ONBOARDING_STARTUP_KEY) === "true",
  );
  const [expandedWhyStepId, setExpandedWhyStepId] = useState<string | null>(null);
  const dashboard = useQuery({ queryKey: ["dashboard-summary"], queryFn: getDashboardSummary, refetchInterval: 10_000 });
  const projects = useQuery({ queryKey: ["projects", tenant.organizationId], queryFn: () => listProjects(tenant.organizationId), enabled: Boolean(tenant.organizationId) });
  const prompts = useQuery({ queryKey: ["asset-registry", "prompts"], queryFn: listPromptAssets });
  const models = useQuery({ queryKey: ["asset-registry", "models"], queryFn: listModelAssets });
  const datasets = useQuery({ queryKey: ["asset-registry", "datasets"], queryFn: listDatasetAssets });
  const experiments = useQuery({ queryKey: ["onboarding-experiments"], queryFn: listExperiments });
  const replays = useQuery({ queryKey: ["onboarding-replays"], queryFn: () => listReplays() });
  const seedDemoData = useMutation({
    mutationFn: seedLocalDemoData,
    onSuccess: async () => {
      await Promise.all([
        dashboard.refetch(),
        projects.refetch(),
        prompts.refetch(),
        models.refetch(),
        datasets.refetch(),
        experiments.refetch(),
        replays.refetch(),
      ]);
    },
  });

  const current = useMemo<Snapshot>(() => {
    const health = dashboard.data?.platformHealth ?? [];
    const metric = (label: string) => dashboard.data?.governanceStatistics.concat(dashboard.data.platformStatistics).find(item => item.label === label)?.value ?? 0;
    const observedAssets = [...(prompts.data ?? []), ...(models.data ?? [])];
    const healthy = (name: string) => health.some(item => item.component === name && item.status === "Healthy");
    return {
      projects: (projects.data ?? []).filter(item => item.status === "ACTIVE").length,
      assets: observedAssets.length + (datasets.data ?? []).length,
      observedAssets: observedAssets.filter(item => item.provenance === "OBSERVED").length,
      experiments: (experiments.data ?? []).length,
      evaluations: metric("Policy Evaluations"),
      decisions: metric("Governance Decisions"),
      replays: (replays.data ?? []).length,
      graphNodes: dashboard.data?.ontologyProjectionStatistics.find(item => item.label === "Graph Nodes")?.value ?? 0,
      apiReady: Boolean(dashboard.data),
      databaseReady: healthy("Database"),
      neo4jReady: healthy("Neo4j Graph Store"),
    };
  }, [dashboard.data, datasets.data, experiments.data, models.data, projects.data, prompts.data, replays.data]);

  const loading = dashboard.isLoading || projects.isLoading || prompts.isLoading || models.isLoading || datasets.isLoading || experiments.isLoading || replays.isLoading;
  const journey = JOURNEYS.find(item => item.id === activeJourneyId) ?? JOURNEYS[0];
  const baseline = progress[journey.id];
  const complete = (step: JourneyStep) =>
    Boolean(manualSteps[journey.id]?.includes(step.id))
    || (Boolean(baseline) && step.complete(current, baseline))
    || Boolean(step.isSystem && step.complete(current, current));
  const completeCount = journey.steps.filter(complete).length;
  const percent = Math.round((completeCount / journey.steps.length) * 100);
  const nextStep = journey.steps.find(step => !complete(step));
  const finished = completeCount === journey.steps.length;
  const seedDataReady = current.assets > 0 && current.decisions > 0 && current.replays > 0 && current.graphNodes > 0;

  function selectJourney(id: string) {
    setActiveJourneyId(id);
    window.localStorage.setItem(ACTIVE_JOURNEY_KEY, id);
  }

  function beginJourney() {
    if (baseline) return;
    const nextProgress = { ...progress, [journey.id]: current };
    setProgress(nextProgress);
    window.localStorage.setItem(JOURNEY_PROGRESS_KEY, JSON.stringify(nextProgress));
  }

  function setStartupPreference(value: boolean) {
    setHideOnStartup(value);
    window.localStorage.setItem(ONBOARDING_STARTUP_KEY, String(value));
  }

  function toggleManualStep(step: JourneyStep) {
    if (step.isSystem) return;
    beginJourney();
    const completed = manualSteps[journey.id] ?? [];
    const next = completed.includes(step.id)
      ? completed.filter(item => item !== step.id)
      : [...completed, step.id];
    const nextManualSteps = { ...manualSteps, [journey.id]: next };
    setManualSteps(nextManualSteps);
    window.localStorage.setItem(JOURNEY_MANUAL_STEPS_KEY, JSON.stringify(nextManualSteps));
  }

  function refreshSeedStatus() {
    void Promise.all([
      dashboard.refetch(),
      projects.refetch(),
      prompts.refetch(),
      models.refetch(),
      datasets.refetch(),
      experiments.refetch(),
      replays.refetch(),
    ]);
  }

  if (!loading && !seedDataReady) {
    return (
      <div className="journey-console flex h-[calc(100vh-4rem)] items-center justify-center p-6">
        <Card className="journey-panel w-full max-w-xl border-primary/30">
          <CardContent className="p-8 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary"><Sparkles className="h-6 w-6" /></div>
            <p className="mt-5 text-sm font-semibold text-primary">Local Studio setup</p>
            <h1 className="mt-2 text-2xl font-semibold">Seed demo data before starting a journey.</h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">The mentor uses a representative end-to-end workflow—assets, evaluations, decisions, replays, and ontology lineage. Your running stack does not have that seed yet.</p>
            <div className="mt-6 border bg-muted/40 p-4 text-left"><p className="font-mono text-xs text-muted-foreground">Run from your AI Governance Control Plane checkout</p><code className="mt-2 block font-mono text-sm">./servers.sh</code></div>
            <p className="mt-4 text-xs leading-5 text-muted-foreground">For a clean local stack, keep <code>AI_GOVERNANCE_AUTO_SEED_DEMO_DATA</code> enabled. The normal launcher performs the complete, idempotent demo seed.</p>
            {seedDemoData.isError ? <p role="alert" className="mt-4 text-sm text-destructive">{seedDemoData.error instanceof Error ? seedDemoData.error.message : "The demo data could not be seeded. Check the local API and try again."}</p> : null}
            <div className="mt-6 flex flex-wrap justify-center gap-3"><Button onClick={() => seedDemoData.mutate()} disabled={seedDemoData.isPending}>{seedDemoData.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}{seedDemoData.isPending ? "Seeding demo data…" : "Seed demo data"}</Button><Button variant="outline" onClick={refreshSeedStatus} disabled={seedDemoData.isPending}>Refresh status</Button><a href={`${docs}/getting-started`} target="_blank" rel="noreferrer"><Button variant="outline">Open setup guide <ExternalLink className="h-4 w-4" /></Button></a></div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="journey-console h-[calc(100vh-4rem)] overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-6 px-6 py-8">
        <header className="journey-chrome flex flex-col justify-between gap-5 border-b pb-7 sm:flex-row sm:items-end">
          <div className="max-w-2xl">
            <div className="flex items-center gap-2 text-primary"><Sparkles className="h-5 w-5" /><span className="text-sm font-semibold">AI Governance Control Plane Mentor</span></div>
            <h1 className="mt-3 text-3xl font-semibold tracking-normal">Build governed workflows!</h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">Studio records a baseline when you begin, then validates only the work created after that point. Existing demo data never completes a journey for you.</p>
          </div>
          <div className="flex flex-col items-start gap-3 sm:items-end">{onOpenDashboard ? <Button className="h-11 px-5 text-base font-bold" onClick={onOpenDashboard}>Open Dashboard</Button> : null}<div className="flex items-center gap-3 text-sm text-muted-foreground"><Route className="h-4 w-4 text-primary" />Current journey: {journey.estimate}</div></div>
        </header>

        <section className="grid gap-3 md:grid-cols-3">
          {JOURNEYS.map(item => {
            const itemBaseline = progress[item.id];
            return <button key={item.id} type="button" onClick={() => selectJourney(item.id)} className={`journey-path border p-4 text-left transition-colors ${item.id === journey.id ? "journey-path-active border-primary bg-primary/5" : "hover:bg-accent"}`}>
              <div className="flex items-center justify-between gap-3"><p className="font-semibold">{item.title}</p><span className="font-mono text-xs text-muted-foreground">{item.estimate}</span></div>
              <p className="mt-2 text-sm leading-5 text-muted-foreground">{item.description}</p>
              <p className="mt-3 text-xs font-medium text-primary">{itemBaseline ? "In progress" : "Start this journey"}</p>
            </button>;
          })}
        </section>

        {finished ? <Card className="journey-panel border-amber-400/45 bg-amber-400/5"><CardContent className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between"><div className="flex gap-3"><PartyPopper className="mt-0.5 h-6 w-6 text-amber-300" /><div><p className="font-mono text-xs uppercase tracking-[0.16em] text-amber-300">Journey outcome</p><h2 className="mt-1 font-semibold">{journey.title} unlocked</h2><p className="mt-1 text-sm text-muted-foreground">Capabilities gained: {journey.unlocks.join(", ")}.</p></div></div><Button variant="outline" onClick={() => selectJourney(JOURNEYS[Math.min(JOURNEYS.indexOf(journey) + 1, JOURNEYS.length - 1)].id)}>Choose next journey</Button></CardContent></Card> : null}

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
          <section><Card className="journey-panel"><CardContent className="p-0">
            <div className="border-b p-5">
              <div className="flex items-end justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold">{journey.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{baseline ? "Progress is validated against your journey baseline." : "Start to capture a baseline from this Studio context."}</p>
                </div>
                <p className="font-mono text-sm text-primary">{completeCount} / {journey.steps.length}</p>
              </div>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-[width] duration-500" style={{ width: `${percent}%` }} /></div>
              <p className="mt-2 text-xs text-muted-foreground">{percent}% complete · runtime state refreshes every 10 seconds</p>
            </div>
            <ol className="divide-y">
              {journey.steps.map((step, index) => {
                const done = complete(step);
                const manual = Boolean(manualSteps[journey.id]?.includes(step.id));
                const whyStepId = `${journey.id}:${step.id}`;
                const whyExpanded = expandedWhyStepId === whyStepId;
                return (
                  <li key={step.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
                    <div className="flex min-w-0 flex-1 items-start gap-3">
                      {step.isSystem ? (
                        loading ? <Loader2 className="mt-0.5 h-5 w-5 animate-spin text-muted-foreground" /> : done ? <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" /> : <Circle className="mt-0.5 h-5 w-5 text-muted-foreground" />
                      ) : (
                        <button type="button" onClick={() => toggleManualStep(step)} aria-pressed={manual} aria-label={`${manual ? "Mark incomplete" : "Mark reviewed"}: ${step.title}`} className="mt-0.5 rounded-full text-muted-foreground transition-colors hover:text-primary">
                          {done ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : <Circle className="h-5 w-5" />}
                        </button>
                      )}
                      <div><div className="flex items-center gap-2"><JourneyStage tone={index}>{String(index + 1).padStart(2, "0")}</JourneyStage><p className="font-medium">{step.title}</p></div><p className="mt-1 text-sm leading-5 text-muted-foreground">{step.explanation}</p><div className="mt-2 flex flex-wrap gap-x-3 gap-y-1"><button type="button" onClick={() => setExpandedWhyStepId(whyExpanded ? null : whyStepId)} aria-expanded={whyExpanded} className="text-xs font-medium text-primary hover:underline">Why?</button><a href={step.docsHref} target="_blank" rel="noreferrer" className="inline-flex items-center text-xs font-medium text-primary hover:underline">Documentation <ExternalLink className="ml-1 h-3 w-3" /></a>{!step.isSystem ? <button type="button" onClick={() => toggleManualStep(step)} className="text-xs font-medium text-muted-foreground hover:text-foreground">{manual ? "Mark incomplete" : "Mark as reviewed"}</button> : null}</div>{whyExpanded ? <div className="mt-3 max-w-2xl border-l-2 border-primary/40 pl-3 text-sm leading-6 text-muted-foreground">{step.why.slice(0, 4).map((line) => <p key={line}>{line}</p>)}</div> : null}</div>
                    </div>
                    <Link href={step.href} onClick={beginJourney} className="shrink-0"><Button variant={done ? "outline" : "default"} size="sm">{!done && step.id === nextStep?.id ? <Play className="h-3.5 w-3.5" /> : null}{done ? "Review" : step.action}</Button></Link>
                  </li>
                );
              })}
            </ol>
            {!baseline ? <div className="border-t p-5"><Button onClick={beginJourney} disabled={loading}><Play className="h-4 w-4" />Start {journey.title}</Button></div> : null}
          </CardContent></Card></section>
          <aside className="space-y-4"><Card className="journey-panel"><CardContent className="p-5"><p className="text-sm font-semibold">Capabilities in this journey</p><div className="mt-4 space-y-3">{journey.unlocks.map(capability => <div key={capability} className="flex items-center gap-2 text-sm">{finished ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <Circle className="h-4 w-4 text-muted-foreground" />}<span className={finished ? "text-foreground" : "text-muted-foreground"}>{capability}</span></div>)}</div></CardContent></Card><Card className="journey-panel"><CardContent className="p-5"><p className="text-sm font-semibold">Need more context?</p><p className="mt-2 text-sm leading-5 text-muted-foreground">Mentor guidance stays in Studio. The detailed reference remains one click away.</p><a href={docs} target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">Read documentation <ExternalLink className="h-3.5 w-3.5" /></a></CardContent></Card></aside>
        </div>
        <div className="border-t pt-5"><label className="flex items-center gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={hideOnStartup} onChange={event => setStartupPreference(event.target.checked)} /> Don&apos;t show journeys on startup</label></div>
      </div>
    </div>
  );
}
