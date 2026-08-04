import { Check, CircleAlert, Clock3, LoaderCircle } from "lucide-react";
import {
  GovernedEventFlow,
  type GovernedFlowStep,
  type GovernedFlowTone,
} from "@/components/governance/GovernedEventFlow";
import type { Experiment, Leaderboard } from "@/lib/api/experiments";

type LifecyclePresentation = {
  activeStep: number;
  outcome: string;
  detail: string;
  tone: Exclude<GovernedFlowTone, "muted">;
};

export function ExperimentLifecycle({
  experiment,
  candidateCount,
  candidatesLoading,
  totalRuns,
  completedRuns,
  failedRuns,
  leaderboard,
  leaderboardLoading,
}: {
  experiment: Experiment;
  candidateCount: number | undefined;
  candidatesLoading: boolean;
  totalRuns: number;
  completedRuns: number;
  failedRuns: number;
  leaderboard: Leaderboard | undefined;
  leaderboardLoading: boolean;
}) {
  const topEntry = leaderboard?.entries[0];
  const presentation = presentationFor({
    experiment,
    candidateCount,
    candidatesLoading,
    totalRuns,
    completedRuns,
    failedRuns,
    topEntry,
    leaderboardLoading,
  });
  const steps = stepsFor({
    candidateCount,
    candidatesLoading,
    totalRuns,
    completedRuns,
    failedRuns,
    activeStep: presentation.activeStep,
    activeTone: presentation.tone,
  });

  return (
    <GovernedEventFlow
      stream="Experiment / evaluation"
      steps={steps}
      outcomeLabel="Latest governed outcome"
      outcome={presentation.outcome}
      outcomeDetail={presentation.detail}
      outcomeTone={presentation.tone}
      activeStep={presentation.activeStep}
      activeAdornment={<StepState tone={presentation.tone} />}
      footer={
        leaderboard && topEntry ? (
          <div className="grid gap-3 text-sm sm:grid-cols-3">
            <Metadata label="Ranking strategy" value={leaderboard.ranking_strategy} />
            <Metadata label="Selected rank" value={`#${topEntry.rank} of ${leaderboard.entries.length}`} />
            <Metadata label="Generated" value={new Date(leaderboard.generated_at).toLocaleString()} />
          </div>
        ) : null
      }
    />
  );
}

function presentationFor({
  experiment,
  candidateCount,
  candidatesLoading,
  totalRuns,
  completedRuns,
  failedRuns,
  topEntry,
  leaderboardLoading,
}: {
  experiment: Experiment;
  candidateCount: number | undefined;
  candidatesLoading: boolean;
  totalRuns: number;
  completedRuns: number;
  failedRuns: number;
  topEntry: Leaderboard["entries"][number] | undefined;
  leaderboardLoading: boolean;
}): LifecyclePresentation {
  if (topEntry) {
    return {
      activeStep: 3,
      outcome: "RECOMMENDED",
      detail: `${topEntry.candidate_id} ranked #${topEntry.rank} with ${Math.round(topEntry.overall_score * 100)}% overall score.`,
      tone: "success",
    };
  }
  if (experiment.status === "FAILED" || failedRuns > 0) {
    return {
      activeStep: 1,
      outcome: "NEEDS REVIEW",
      detail: `${failedRuns} evaluation ${failedRuns === 1 ? "run has" : "runs have"} failed. Resolve the run issue before comparing results.`,
      tone: "danger",
    };
  }
  if (candidatesLoading || leaderboardLoading) {
    return {
      activeStep: candidateCount ? 2 : 0,
      outcome: "LOADING",
      detail: "Resolving the current experiment state and governed outcome.",
      tone: "progress",
    };
  }
  if (!candidateCount) {
    return {
      activeStep: 0,
      outcome: "READY TO CONFIGURE",
      detail: "Add one or more governed candidate configurations to begin the experiment.",
      tone: "info",
    };
  }
  if (!totalRuns) {
    return {
      activeStep: 1,
      outcome: "READY TO EVALUATE",
      detail: "Candidate configurations are registered and ready for evaluation runs.",
      tone: "info",
    };
  }
  if (completedRuns + failedRuns < totalRuns) {
    return {
      activeStep: 1,
      outcome: "EVALUATING",
      detail: "Evaluation runs are still producing governed evidence for comparison.",
      tone: "progress",
    };
  }
  return {
    activeStep: 2,
    outcome: "AWAITING RANKING",
    detail: "Evaluation evidence is complete and is ready to be compared into a leaderboard outcome.",
    tone: "warning",
  };
}

function stepsFor({
  candidateCount,
  candidatesLoading,
  totalRuns,
  completedRuns,
  failedRuns,
  activeStep,
  activeTone,
}: {
  candidateCount: number | undefined;
  candidatesLoading: boolean;
  totalRuns: number;
  completedRuns: number;
  failedRuns: number;
  activeStep: number;
  activeTone: Exclude<GovernedFlowTone, "muted">;
}): GovernedFlowStep[] {
  const base: GovernedFlowStep[] = [
    {
      id: "candidates",
      label: "configure candidates",
      detail: candidatesLoading
        ? "Loading governed candidate configurations."
        : `${candidateCount ?? 0} configuration${candidateCount === 1 ? "" : "s"} registered for comparison.`,
      tone: "info",
    },
    {
      id: "evaluate",
      label: "run evaluations",
      detail: totalRuns
        ? `${completedRuns} completed · ${failedRuns} failed · ${totalRuns} total runs.`
        : "Evaluation runs produce durable evidence for each candidate.",
      tone: "progress",
    },
    {
      id: "compare",
      label: "compare results",
      detail: "Compatible evaluation evidence is ranked using the configured strategy.",
      tone: "info",
    },
    {
      id: "recommend",
      label: "publish recommendation",
      detail: "The leading candidate is retained as an explainable, non-deploying outcome.",
      tone: "success",
    },
  ];

  return base.map((step, index) => ({
    ...step,
    tone: index === activeStep ? activeTone : index > activeStep ? "muted" : step.tone,
  }));
}

function StepState({ tone }: { tone: Exclude<GovernedFlowTone, "muted"> }) {
  if (tone === "success") {
    return <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" aria-label="Completed" />;
  }
  if (tone === "danger") {
    return <CircleAlert className="h-3.5 w-3.5 text-destructive" aria-label="Needs review" />;
  }
  if (tone === "progress") {
    return <LoaderCircle className="h-3.5 w-3.5 animate-spin text-violet-600 dark:text-violet-400" aria-label="In progress" />;
  }
  return <Clock3 className="h-3.5 w-3.5 text-cyan-600 dark:text-cyan-400" aria-label="Awaiting action" />;
}

function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-sm">{value}</p>
    </div>
  );
}
