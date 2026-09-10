import { Check, CircleAlert, Clock3, LoaderCircle } from "lucide-react";
import {
  GovernedEventFlow,
  type GovernedFlowStep,
  type GovernedFlowTone,
} from "@/components/governance/GovernedEventFlow";
import type { Candidate, Experiment, Leaderboard } from "@/lib/api/experiments";

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
  candidates,
}: {
  experiment: Experiment;
  candidateCount: number | undefined;
  candidatesLoading: boolean;
  totalRuns: number;
  completedRuns: number;
  failedRuns: number;
  leaderboard: Leaderboard | undefined;
  leaderboardLoading: boolean;
  candidates: Candidate[];
}) {
  const topEntry = leaderboard?.entries[0];
  const canCompare = (candidateCount ?? 0) >= 2;
  const hasTopTie = Boolean(
    topEntry &&
      leaderboard?.entries.slice(1).some((entry) => entry.overall_score === topEntry.overall_score),
  );
  const candidateNameById = new Map(candidates.map((candidate) => [candidate.candidate_id, candidate.candidate_name]));
  const presentation = presentationFor({
    experiment,
    candidateCount,
    candidatesLoading,
    totalRuns,
    completedRuns,
    failedRuns,
    topEntry,
    leaderboardLoading,
    hasTopTie,
    topCandidateName: topEntry ? candidateNameById.get(topEntry.candidate_id) : undefined,
  });
  const steps = stepsFor({
    candidateCount,
    candidatesLoading,
    totalRuns,
    completedRuns,
    failedRuns,
    hasTopTie,
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
            <Metadata
              label={hasTopTie ? "Top outcome" : canCompare ? "Selected rank" : "Observed rank"}
              value={hasTopTie ? "Tie — no unique winner" : `#${topEntry.rank} of ${leaderboard.entries.length}`}
            />
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
  hasTopTie,
  topCandidateName,
}: {
  experiment: Experiment;
  candidateCount: number | undefined;
  candidatesLoading: boolean;
  totalRuns: number;
  completedRuns: number;
  failedRuns: number;
  topEntry: Leaderboard["entries"][number] | undefined;
  leaderboardLoading: boolean;
  hasTopTie: boolean;
  topCandidateName: string | undefined;
}): LifecyclePresentation {
  if (candidatesLoading || leaderboardLoading) {
    return {
      activeStep: candidateCount ? 2 : 0,
      outcome: "LOADING",
      detail: "Resolving the current experiment state and governed outcome.",
      tone: "progress",
    };
  }
  if (topEntry && (candidateCount ?? 0) >= 2 && hasTopTie) {
    return {
      activeStep: 2,
      outcome: "NO UNIQUE WINNER",
      detail: "The leading candidates have the same quality ranking value. Review efficiency evidence before selecting one.",
      tone: "warning",
    };
  }
  if (topEntry && (candidateCount ?? 0) >= 2) {
    return {
      activeStep: 3,
      outcome: "RECOMMENDED",
      detail: `${topCandidateName ?? "The leading candidate"} ranked #${topEntry.rank} with ranking value ${formatRankingValue(topEntry.overall_score)}.`,
      tone: "success",
    };
  }
  if (topEntry && candidateCount === 1) {
    return {
      activeStep: 2,
      outcome: "COMPARISON REQUIRED",
      detail: "One candidate has evaluation evidence. Add a second candidate before making a recommendation.",
      tone: "warning",
    };
  }
  if (experiment.status === "CANCELLED") {
    return {
      activeStep: 1,
      outcome: "CANCELLED",
      detail: "The experiment was cancelled. Any evidence already produced remains available for review, but no recommendation is generated.",
      tone: "warning",
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
  hasTopTie,
  activeStep,
  activeTone,
}: {
  candidateCount: number | undefined;
  candidatesLoading: boolean;
  totalRuns: number;
  completedRuns: number;
  failedRuns: number;
  hasTopTie: boolean;
  activeStep: number;
  activeTone: Exclude<GovernedFlowTone, "muted">;
}): GovernedFlowStep[] {
  const canCompare = (candidateCount ?? 0) >= 2;
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
      detail: canCompare
        ? "Compatible evaluation evidence is ranked using the configured strategy."
        : "Add a second candidate before interpreting this as a comparison.",
      tone: "info",
    },
    {
      id: "recommend",
      label: canCompare && !hasTopTie ? "publish recommendation" : "comparison required",
      detail: canCompare
        ? hasTopTie
          ? "A quality tie requires human review of the operational trade-offs."
          : "The leading candidate is retained as an explainable, non-deploying outcome."
        : "A single candidate can be observed, but cannot receive a comparative recommendation.",
      tone: canCompare && !hasTopTie ? "success" : "warning",
    },
  ];

  return base.map((step, index) => ({
    ...step,
    tone: index === activeStep ? activeTone : index > activeStep ? "muted" : step.tone,
  }));
}

function formatRankingValue(value: number): string {
  return value.toLocaleString(undefined, {
    maximumFractionDigits: 4,
  });
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
