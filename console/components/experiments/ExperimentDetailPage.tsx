"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  CircleCheck,
  CircleX,
  Play,
  RefreshCw,
  Trophy,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import {
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

import { ExperimentStatusBadge } from "@/components/experiments/ExperimentStatusBadge";
import { ExperimentLifecycle } from "@/components/experiments/ExperimentLifecycle";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  addCandidate,
  cancelExperiment,
  getCandidateComparison,
  getExperiment,
  getLeaderboard,
  getRunPlan,
  listCandidates,
  listRunEvaluations,
  listRuns,
  runExperiment,
} from "@/lib/api/experiments";
import type {
  Candidate,
  CandidateComparison,
  MetricComparison,
} from "@/lib/api/experiments";
import {
  listDatasetAssets,
  listModelAssets,
  listPromptAssets,
  listProviderInstallations,
} from "@/lib/api/registries";
import { listRuntimeConnections } from "@/lib/api/runtime-connections";

const TABS = [
  "Overview",
  "Candidates",
  "Evaluation Runs",
  "Comparison",
  "Leaderboard",
];

type CandidateDraft = {
  candidate_name: string;
  prompt_version: string;
  model_version: string;
  dataset_version: string;
  provider_name: string;
  provider_installation_id: string;
  runtime_connection_id: string;
  runtime_parameters: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

const INITIAL_CANDIDATE: CandidateDraft = {
  candidate_name: "",
  prompt_version: "",
  model_version: "",
  dataset_version: "",
  provider_name: "",
  provider_installation_id: "",
  runtime_connection_id: "",
  runtime_parameters: {},
  metadata: {},
};

const DEFAULT_RUN_COLUMN_WIDTHS = {
  runId: 250,
  candidate: 300,
  status: 135,
  started: 190,
  duration: 105,
  progress: 205,
  failureReason: 340,
} as const;

type RunColumnKey = keyof typeof DEFAULT_RUN_COLUMN_WIDTHS;

const MIN_RUN_COLUMN_WIDTHS: Record<RunColumnKey, number> = {
  runId: 160,
  candidate: 180,
  status: 110,
  started: 150,
  duration: 90,
  progress: 160,
  failureReason: 240,
};

function ResizableRunColumnHeader({
  column,
  children,
  width,
  onResizeStart,
  onResizeBy,
}: {
  column: RunColumnKey;
  children: ReactNode;
  width: number;
  onResizeStart: (
    event: ReactPointerEvent<HTMLDivElement>,
    column: RunColumnKey,
  ) => void;
  onResizeBy: (column: RunColumnKey, amount: number) => void;
}) {
  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
      return;
    }

    event.preventDefault();
    onResizeBy(column, event.key === "ArrowLeft" ? -20 : 20);
  };

  return (
    <th className="relative px-2 py-2 font-medium" style={{ width }}>
      {children}
      <div
        aria-label={`Resize ${String(children)} column`}
        aria-orientation="vertical"
        aria-valuemin={MIN_RUN_COLUMN_WIDTHS[column]}
        aria-valuenow={width}
        className="absolute inset-y-0 right-0 z-10 w-3 cursor-col-resize touch-none border-r border-transparent hover:border-primary focus-visible:border-primary focus-visible:outline-none"
        onKeyDown={handleKeyDown}
        onPointerDown={(event) => onResizeStart(event, column)}
        role="separator"
        tabIndex={0}
      />
    </th>
  );
}

const EVALUATION_METRIC_LABELS: Record<string, string> = {
  input_tokens: "Input tokens",
  output_tokens: "Output tokens",
  total_tokens: "Total tokens",
  tool_action_count: "Tool actions",
  wall_clock_duration_seconds: "Wall clock (s)",
};

function formatEvaluationMetricLabel(name: string) {
  return (
    EVALUATION_METRIC_LABELS[name] ??
    name
      .split("_")
      .filter(Boolean)
      .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
      .join(" ")
  );
}

export function ExperimentDetailPage({
  experimentId,
}: {
  experimentId: string;
}) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("Overview");
  const [candidate, setCandidate] = useState<CandidateDraft>(
    INITIAL_CANDIDATE,
  );
  const [runnerVariantJson, setRunnerVariantJson] = useState("{}");
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [runSubmitted, setRunSubmitted] = useState(false);
  const [repetitions, setRepetitions] = useState(1);
  const [refreshInterval, setRefreshInterval] = useState<"5" | "10" | "never">("5");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [evaluationPage, setEvaluationPage] = useState(1);
  const [runColumnWidths, setRunColumnWidths] = useState<
    Record<RunColumnKey, number>
  >({ ...DEFAULT_RUN_COLUMN_WIDTHS });
  const [baselineCandidateId, setBaselineCandidateId] = useState("");
  const [comparisonCandidateId, setComparisonCandidateId] = useState("");

  const resizeRunColumn = (column: RunColumnKey, amount: number) => {
    setRunColumnWidths((current) => ({
      ...current,
      [column]: Math.max(
        MIN_RUN_COLUMN_WIDTHS[column],
        current[column] + amount,
      ),
    }));
  };

  const startRunColumnResize = (
    event: ReactPointerEvent<HTMLDivElement>,
    column: RunColumnKey,
  ) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = runColumnWidths[column];
    const onPointerMove = (moveEvent: PointerEvent) => {
      setRunColumnWidths((current) => ({
        ...current,
        [column]: Math.max(
          MIN_RUN_COLUMN_WIDTHS[column],
          startWidth + moveEvent.clientX - startX,
        ),
      }));
    };
    const onPointerUp = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  };
  const runTableWidth = Object.values(runColumnWidths).reduce(
    (total, width) => total + width,
    0,
  );

  const experiment = useQuery({
    queryKey: ["experiment", experimentId],
    queryFn: () => getExperiment(experimentId),
  });
  const autoRefreshMs = refreshInterval === "never" ? false : Number(refreshInterval) * 1000;
  const candidates = useQuery({
    queryKey: ["candidates", experimentId],
    queryFn: () => listCandidates(experimentId),
    enabled: tab === "Overview" || tab === "Candidates" || tab === "Comparison",
  });
  const runs = useQuery({
    queryKey: ["runs", experimentId],
    queryFn: () => listRuns(experimentId),
    enabled: tab === "Evaluation Runs" || tab === "Overview" || runSubmitted,
    refetchInterval:
      experiment.data?.status === "RUNNING" || runSubmitted ? autoRefreshMs : false,
  });
  const runPlan = useQuery({
    queryKey: ["experiment-run-plan", experimentId],
    queryFn: () => getRunPlan(experimentId),
    refetchInterval:
      experiment.data?.status === "RUNNING" || runSubmitted ? autoRefreshMs : false,
  });
  const leaderboard = useQuery({
    queryKey: ["leaderboard", experimentId],
    queryFn: () => getLeaderboard(experimentId),
    enabled: tab === "Overview" || tab === "Leaderboard",
  });
  const comparisonReady =
    Boolean(baselineCandidateId) &&
    Boolean(comparisonCandidateId) &&
    baselineCandidateId !== comparisonCandidateId;
  const comparison = useQuery({
    queryKey: [
      "candidate-comparison",
      experimentId,
      baselineCandidateId,
      comparisonCandidateId,
    ],
    queryFn: () =>
      getCandidateComparison(
        experimentId,
        baselineCandidateId,
        comparisonCandidateId,
      ),
    enabled: tab === "Comparison" && comparisonReady,
  });
  const activeResultRunId = selectedRunId || runs.data?.[0]?.run_id || "";
  const runEvaluations = useQuery({
    queryKey: ["run-evaluations", experimentId, activeResultRunId, evaluationPage],
    queryFn: () => listRunEvaluations(experimentId, activeResultRunId, evaluationPage),
    enabled: tab === "Evaluation Runs" && Boolean(activeResultRunId),
    refetchInterval: tab === "Evaluation Runs" ? autoRefreshMs : false,
  });
  const evaluationResults = runEvaluations.data;

  const prompts = useQuery({
    queryKey: ["prompt-assets"],
    queryFn: listPromptAssets,
    enabled: tab === "Candidates" && experiment.data?.status === "DRAFT",
  });
  const models = useQuery({
    queryKey: ["model-assets"],
    queryFn: listModelAssets,
    enabled: tab === "Candidates" && experiment.data?.status === "DRAFT",
  });
  const datasets = useQuery({
    queryKey: ["dataset-assets"],
    queryFn: listDatasetAssets,
    enabled: tab === "Candidates" && experiment.data?.status === "DRAFT",
  });
  const providerInstallations = useQuery({
    queryKey: ["provider-installations"],
    queryFn: listProviderInstallations,
    enabled: tab === "Candidates" && experiment.data?.status === "DRAFT",
  });
  const runtimeConnections = useQuery({
    queryKey: ["runtime-connections"],
    queryFn: listRuntimeConnections,
    enabled: tab === "Candidates" && experiment.data?.status === "DRAFT",
  });
  const activePrompts = (prompts.data ?? []).filter(
    (item) => item.status === "ACTIVE",
  );
  const activeModels = (models.data ?? []).filter(
    (item) => item.status === "ACTIVE",
  );
  const eligibleDatasets = (datasets.data ?? []).filter(
    (item) => item.status === "ACTIVE" || item.status === "FROZEN",
  );
  const selectedModel = activeModels.find(
    (item) => `${item.model_id}:${item.version}` === candidate.model_version,
  );
  const selectedModelProvider = selectedModel
    ? runtimeProviderKey(selectedModel.provider)
    : null;
  const requiresCandidateRuntimeConnection = ["openai", "anthropic", "custom"].includes(
    selectedModelProvider ?? "",
  );
  const compatibleRuntimeConnections = selectedModelProvider
    ? (runtimeConnections.data ?? []).filter(
        (item) =>
          item.enabled && runtimeProviderKey(item.provider) === selectedModelProvider,
      )
    : [];
  const selectedProviderInstallation = (providerInstallations.data ?? []).find(
    (item) => item.installation_id === candidate.provider_installation_id,
  );

  const add = useMutation({
    mutationFn: () => addCandidate(experimentId, candidate),
    onSuccess: async () => {
      setCandidate({ ...candidate, candidate_name: "" });
      setRunnerVariantJson("{}");
      setError(null);
      await queryClient.invalidateQueries({
        queryKey: ["candidates", experimentId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["experiment", experimentId],
      });
    },
    onError: (cause) =>
      setError(
        cause instanceof Error ? cause.message : "Unable to add candidate.",
      ),
  });

  const run = useMutation({
    mutationFn: () => runExperiment(experimentId, repetitions),
    onMutate: () => {
      setRunSubmitted(true);
      setError(null);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["experiment", experimentId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["candidates", experimentId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["runs", experimentId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["leaderboard", experimentId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["candidate-comparison", experimentId],
      });
    },
    onSettled: async () => {
      setRunSubmitted(false);
      await queryClient.invalidateQueries({
        queryKey: ["experiment-run-plan", experimentId],
      });
    },
    onError: (cause) =>
      setError(
        cause instanceof Error ? cause.message : "Unable to run experiment.",
      ),
  });

  const cancel = useMutation({
    mutationFn: () => cancelExperiment(experimentId),
    onSuccess: async () => {
      setRunSubmitted(false);
      setError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["experiment", experimentId] }),
        queryClient.invalidateQueries({ queryKey: ["runs", experimentId] }),
        queryClient.invalidateQueries({ queryKey: ["leaderboard", experimentId] }),
        queryClient.invalidateQueries({ queryKey: ["candidate-comparison", experimentId] }),
      ]);
    },
    onError: (cause) =>
      setError(
        cause instanceof Error ? cause.message : "Unable to cancel experiment.",
      ),
  });

  if (experiment.isLoading) {
    return <div className="p-8 text-sm text-muted-foreground">Loading experiment…</div>;
  }

  if (experiment.isError || !experiment.data) {
    return (
      <div className="p-8 text-sm text-destructive">
        Experiment not found or unavailable.
      </div>
    );
  }

  const experimentData = experiment.data;
  const totalCandidates = candidates.data?.length;
  const totalRuns = runs.data?.length ?? 0;
  const completedRuns =
    runs.data?.filter((item) => item.status === "COMPLETED").length ?? 0;
  const failedRuns =
    runs.data?.filter(
      (item) =>
        item.status === "FAILED" || item.status === "EXECUTION_FAILED",
    ).length ?? 0;
  const successRate = totalRuns
    ? Math.round((completedRuns / totalRuns) * 100)
    : null;
  const topEntry = leaderboard.data?.entries[0];
  const activeRun = runPlan.data?.active_run;
  const activeRunTotal = activeRun?.total_item_count ?? runPlan.data?.dataset_item_count ?? 0;
  const activeRunProgress = activeRun && activeRunTotal
    ? Math.round((activeRun.completed_item_count / activeRunTotal) * 100)
    : 0;
  const metadataEntries = Object.entries(experimentData.metadata ?? {});

  async function refreshExperiment() {
    setError(null);
    setRefreshing(true);
    await Promise.allSettled([
      queryClient.refetchQueries({
        queryKey: ["experiment", experimentId],
        type: "all",
      }),
      queryClient.refetchQueries({
        queryKey: ["candidates", experimentId],
        type: "all",
      }),
      queryClient.refetchQueries({
        queryKey: ["runs", experimentId],
        type: "all",
      }),
      queryClient.refetchQueries({
        queryKey: ["leaderboard", experimentId],
        type: "all",
      }),
      queryClient.refetchQueries({
        queryKey: ["candidate-comparison", experimentId],
        type: "all",
      }),
      queryClient.refetchQueries({
        queryKey: ["experiment-run-plan", experimentId],
        type: "all",
      }),
      queryClient.refetchQueries({
        queryKey: ["run-evaluations", experimentId],
        type: "all",
      }),
    ]);
    setRefreshing(false);
  }

  return (
    <div className="studio-page flex flex-col gap-5">
      <Link
        href="/experiments"
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Experiments
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{experimentData.name}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {experimentData.description}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <ExperimentStatusBadge status={experimentData.status} />
            <code className="text-xs text-muted-foreground">
              {experimentData.experiment_id}
            </code>
            <CopyButton
              value={experimentData.experiment_id}
              variant="ghost"
              size="sm"
              label="Copy ID"
              copyTitle="Copy experiment ID"
              iconClassName="h-3 w-3"
            />
          </div>
        </div>

        <div className="flex gap-2">
          {experimentData.status === "DRAFT" && (
            <label className="grid gap-1 text-xs text-muted-foreground">
              Repetitions
              <Input
                aria-label="Experiment repetitions"
                className="h-9 w-20"
                min={1}
                max={100}
                type="number"
                value={repetitions}
                onChange={(event) => setRepetitions(Math.max(1, Number(event.target.value) || 1))}
              />
            </label>
          )}
          <Button
            variant="outline"
            disabled={refreshing}
            onClick={() => void refreshExperiment()}
          >
            <RefreshCw className="h-4 w-4" />
            {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
          {experimentData.status === "DRAFT" && (
            <Button
              disabled={
                run.isPending || candidates.isLoading || runPlan.isLoading || (totalCandidates ?? 0) === 0
              }
              title={(totalCandidates ?? 0) === 0 ? "Add at least one candidate before starting this experiment." : undefined}
              onClick={() => {
                const plan = runPlan.data;
                if (!plan) return;
                const message = `This experiment will make ${plan.model_invocation_count * repetitions} model invocation${plan.model_invocation_count * repetitions === 1 ? "" : "s"} (${plan.candidate_count} candidate${plan.candidate_count === 1 ? "" : "s"} × ${plan.dataset_item_count} dataset item${plan.dataset_item_count === 1 ? "" : "s"} × ${repetitions} repetition${repetitions === 1 ? "" : "s"}). Each output will also be sent to the configured evaluator. Provider charges may apply. Continue?`;
                if (window.confirm(message)) run.mutate();
              }}
            >
              <Play className="h-4 w-4" />
              {run.isPending ? "Running…" : "Start Experiment"}
            </Button>
          )}
          {experimentData.status === "RUNNING" && (
            <Button
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={cancel.isPending}
              onClick={() => {
                if (window.confirm("Cancel this experiment? Any evidence already captured will be retained, but no further candidate or evaluator calls will be started.")) {
                  cancel.mutate();
                }
              }}
            >
              <CircleX className="h-4 w-4" />
              {cancel.isPending ? "Cancelling…" : "Cancel Experiment"}
            </Button>
          )}
        </div>
      </div>

      <div className="flex gap-1 overflow-x-auto border-b">
        {TABS.map((item) => (
          <button
            key={item}
            className={`px-3 py-2 text-sm ${
              tab === item
                ? "border-b-2 border-primary font-medium"
                : "text-muted-foreground"
            }`}
            onClick={() => setTab(item)}
          >
            {item}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {tab === "Overview" && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              icon={Users}
              label="Candidates"
              value={totalCandidates ?? "—"}
              description="Configurations under comparison"
            />
            <MetricCard
              icon={Activity}
              label="Evaluation runs"
              value={runs.isLoading ? "—" : totalRuns}
              description="Completed and failed executions"
            />
            <MetricCard
              icon={CircleCheck}
              label="Success rate"
              value={successRate === null ? "—" : `${successRate}%`}
              description={
                totalRuns ? `${completedRuns} of ${totalRuns} completed` : "No runs yet"
              }
            />
            <MetricCard
              icon={Trophy}
              label="Ranking value"
              value={topEntry ? formatRankingValue(topEntry.overall_score) : "—"}
              description={topEntry ? "Composite value · not a percentage" : "No leaderboard yet"}
            />
          </div>

          <ExperimentLifecycle
            experiment={experimentData}
            candidateCount={totalCandidates}
            candidatesLoading={candidates.isLoading}
            totalRuns={totalRuns}
            completedRuns={completedRuns}
            failedRuns={failedRuns}
            leaderboard={leaderboard.data}
            leaderboardLoading={leaderboard.isLoading}
          />

          {runPlan.data && (
            <Card>
              <CardHeader>
                <CardTitle>
                  {activeRun ? "Live Execution Progress" : "Run Plan"}
                </CardTitle>
                <CardDescription>
                  {activeRun
                    ? `Candidate ${activeRun.candidate_position} of ${runPlan.data.candidate_count}: ${activeRun.candidate_name}`
                    : runPlan.data.workload_basis === "PROVIDER_DECLARED"
                      ? "The provider's bounded task configuration defines this workload."
                      : "The declared workload is calculated from the immutable dataset version."}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {activeRun ? (
                  <>
                    <div className="flex flex-wrap justify-between gap-2 text-sm">
                      <span>
                        Model execution: {activeRun.completed_item_count} of {activeRunTotal} dataset items
                      </span>
                      <span className="text-muted-foreground">
                        Evaluation evidence: {activeRun.evaluated_item_count} of {activeRunTotal}
                      </span>
                    </div>
                    <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: `${activeRunProgress}%` }}
                      />
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">
                      Progress is persisted after every model invocation and is refreshed automatically while the experiment is running.
                    </p>
                  </>
                ) : (
                  <div className="grid gap-3 text-sm sm:grid-cols-3">
                    <DetailItem label="Runner invocations" value={runPlan.data.runner_invocation_count} />
                    <DetailItem
                      label="Expected sample results"
                      value={runPlan.data.expected_sample_result_count ?? "Provider does not declare a bound"}
                    />
                    <DetailItem
                      label={runPlan.data.workload_basis === "PROVIDER_DECLARED" ? "Control-plane dataset items" : "Dataset items"}
                      value={runPlan.data.dataset_item_count}
                    />
                  </div>
                )}
                {runPlan.data.workload_basis === "PROVIDER_DECLARED" && !activeRun && (
                  <p className="mt-3 text-xs text-muted-foreground">
                    This provider can run its own packaged task set. The control-plane dataset count is retained for lineage and does not define the provider workload.
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          <div className="grid gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Experiment Details</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
                  <DetailItem
                    label="Status"
                    value={<ExperimentStatusBadge status={experimentData.status} />}
                  />
                  <DetailItem label="Owner" value={experimentData.owner} />
                  <DetailItem
                    label="Created"
                    value={new Date(experimentData.created_at).toLocaleString()}
                  />
                  <DetailItem
                    label="Last modified"
                    value={new Date(
                      experimentData.updated_at ?? experimentData.created_at,
                    ).toLocaleString()}
                  />
                </div>

                <div className="mt-6 border-t pt-5">
                  <div className="mb-2 flex items-center justify-between text-sm">
                    <span className="font-medium">Execution health</span>
                    <span className="text-muted-foreground">
                      {totalRuns ? `${successRate}% successful` : "Not started"}
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-[#32d74b] transition-all"
                      style={{ width: `${successRate ?? 0}%` }}
                    />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5">
                      <CircleCheck className="h-3.5 w-3.5 text-[#32d74b]" />
                      {completedRuns} completed
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <CircleX className="h-3.5 w-3.5 text-[#ff453a]" />
                      {failedRuns} failed
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Metadata</CardTitle>
            </CardHeader>
            <CardContent>
              {metadataEntries.length === 0 ? (
                <div className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">
                  No metadata has been recorded for this experiment.
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {metadataEntries.map(([key, value]) => (
                    <div key={key} className="min-w-0 rounded-lg bg-muted/50 p-3">
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {key}
                      </p>
                      <p className="mt-1 break-words text-sm">
                        {typeof value === "object"
                          ? JSON.stringify(value)
                          : String(value)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {tab === "Candidates" && (
        <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
          <Card>
            <CardHeader>
              <CardTitle>Candidates</CardTitle>
              <CardDescription>
                Governed configurations registered for this experiment.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {candidates.isLoading ? (
                <p className="p-6 text-sm text-muted-foreground">
                  Loading candidates…
                </p>
              ) : candidates.data?.length === 0 ? (
                <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                  No candidates have been added to this experiment yet.
                </div>
              ) : (
                (candidates.data ?? []).map((item) => (
                  <CandidateCard key={item.candidate_id} candidate={item} />
                ))
              )}
            </CardContent>
          </Card>

          {experimentData.status === "DRAFT" && (
            <Card>
              <CardHeader>
                <CardTitle>Add Candidate</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <Input
                  placeholder="Candidate name"
                  value={candidate.candidate_name}
                  onChange={(event) =>
                    setCandidate({
                      ...candidate,
                      candidate_name: event.target.value,
                    })
                  }
                />
                <AssetSelect
                  label="Prompt version"
                  value={candidate.prompt_version}
                  loading={prompts.isLoading}
                  options={activePrompts.map((item) => ({
                    value: `${item.prompt_id}:${item.version}`,
                    label: `${item.name} · ${item.version}`,
                  }))}
                  onChange={(value) =>
                    setCandidate({ ...candidate, prompt_version: value })
                  }
                />
                <AssetSelect
                  label="Model version"
                  value={candidate.model_version}
                  loading={models.isLoading}
                  options={activeModels.map((item) => ({
                    value: `${item.model_id}:${item.version}`,
                    label: `${item.provider} / ${item.model_name} · ${item.version}`,
                  }))}
                  onChange={(value) =>
                    setCandidate({
                      ...candidate,
                      model_version: value,
                      runtime_connection_id: "",
                      runtime_parameters: {},
                    })
                  }
                />
                <AssetSelect
                  label="Dataset version"
                  value={candidate.dataset_version}
                  loading={datasets.isLoading}
                  options={eligibleDatasets.map((item) => ({
                    value: `${item.dataset_id}:${item.version}`,
                    label: `${item.name} · ${item.version}`,
                  }))}
                  onChange={(value) =>
                    setCandidate({ ...candidate, dataset_version: value })
                  }
                />
                <AssetSelect
                  label="Provider installation"
                  value={candidate.provider_installation_id}
                  loading={providerInstallations.isLoading}
                  options={(providerInstallations.data ?? []).filter((item) => item.enabled).map((item) => ({ value: item.installation_id, label: `${item.display_name} · ${item.provider_type}` }))}
                  onChange={(value) => setCandidate({ ...candidate, provider_installation_id: value, provider_name: "" })}
                />
                {selectedProviderInstallation?.provider_type === "inspect_ai" ? (
                  <label className="grid gap-1 text-sm">
                    Inspect runner variant JSON
                    <span className="text-xs text-muted-foreground">
                      Vary only solver/scaffold fields here. Fixed model, tasks, scorer,
                      and limits belong to the shared installation.
                    </span>
                    <textarea
                      aria-label="Inspect runner variant JSON"
                      className="min-h-24 rounded-md border bg-background p-2 font-mono text-xs"
                      value={runnerVariantJson}
                      onChange={(event) => {
                        setRunnerVariantJson(event.target.value);
                        try {
                          const value = JSON.parse(event.target.value) as Record<string, unknown>;
                          setCandidate({
                            ...candidate,
                            metadata: {
                              ...candidate.metadata,
                              evaluation_runner_config: value,
                            },
                          });
                          setError(null);
                        } catch {
                          setError("Inspect runner variant JSON must be an object.");
                        }
                      }}
                    />
                  </label>
                ) : null}
                <AssetSelect
                  label={requiresCandidateRuntimeConnection ? "Runtime connection (required, matching provider only)" : "Runtime connection (matching provider only)"}
                  value={candidate.runtime_connection_id}
                  loading={runtimeConnections.isLoading}
                  emptyOptionLabel={
                    selectedModel
                      ? `No active connection for ${selectedModel.provider}`
                      : "Select a model version first"
                  }
                  options={compatibleRuntimeConnections
                    .map((item) => ({
                      value: item.runtime_connection_id,
                      label: `${item.display_name} · ${item.provider}`,
                    }))}
                  onChange={(value) =>
                    setCandidate({ ...candidate, runtime_connection_id: value })
                  }
                />
                {selectedModel?.runtime_capabilities ? (
                  <div className="rounded-md border p-3 text-xs">
                    <p className="font-medium">Candidate runtime controls</p>
                    <p className="mt-1 text-muted-foreground">
                      {selectedModel.runtime_capabilities.invocation_contract} · {selectedModel.runtime_capabilities.verification.toLowerCase()}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {selectedModel.runtime_capabilities.parameters.map((parameter) => (
                        <span key={parameter.name} className="rounded bg-muted px-2 py-1">
                          {parameter.name.replaceAll("_", " ")}: {parameter.supported ? "supported" : "provider default"}
                        </span>
                      ))}
                    </div>
                    {selectedModel.runtime_capabilities.parameters
                      .filter((parameter) => parameter.supported)
                      .map((parameter) => (
                        <label key={parameter.name} className="mt-3 grid gap-1 text-sm">
                          {parameter.name.replaceAll("_", " ")}
                          <Input
                            type="number"
                            min={parameter.minimum ?? undefined}
                            max={parameter.maximum ?? undefined}
                            step={parameter.value_type === "integer" ? 1 : "any"}
                            value={String(candidate.runtime_parameters[parameter.name] ?? "")}
                            placeholder={parameter.default == null ? "Provider default" : String(parameter.default)}
                            onChange={(event) => {
                              const runtimeParameters = { ...candidate.runtime_parameters };
                              if (!event.target.value) delete runtimeParameters[parameter.name];
                              else runtimeParameters[parameter.name] = Number(event.target.value);
                              setCandidate({ ...candidate, runtime_parameters: runtimeParameters });
                            }}
                          />
                        </label>
                      ))}
                  </div>
                ) : null}
                <p className="text-xs text-muted-foreground">
                  {selectedModelProvider === "mock"
                    ? "Mock models do not use Runtime Connections."
                    : <>
                        Required for candidate execution. Select a compatible, active
                        model runtime configured in{" "}
                        <Link className="text-primary underline" href="/settings">
                          Settings → Runtime Connections
                        </Link>
                        .
                      </>}
                </p>
                {!providerInstallations.isLoading && !(providerInstallations.data ?? []).some((item) => item.enabled) ? <p className="text-sm text-muted-foreground">Create and enable a provider installation in <Link className="text-primary underline" href="/assets/providers">Evaluation Providers</Link> before adding a candidate.</p> : null}
                <Button
                  className="w-full"
                  disabled={
                    add.isPending ||
                    !candidate.candidate_name.trim() ||
                    !candidate.prompt_version ||
                    !candidate.model_version ||
                    !candidate.dataset_version ||
                    !candidate.provider_installation_id ||
                    (requiresCandidateRuntimeConnection && !candidate.runtime_connection_id)
                  }
                  onClick={() => add.mutate()}
                >
                  {add.isPending ? "Adding…" : "Add Candidate"}
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {tab === "Evaluation Runs" && (
        <div className="space-y-4">
        <Card>
          <CardHeader className="flex-row items-center justify-between gap-4">
            <div>
              <CardTitle>Evaluation Runs</CardTitle>
              <CardDescription>
                Run state and durable execution progress. Drag a column divider
                to resize it.
              </CardDescription>
            </div>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              Refresh
              <select
                aria-label="Evaluation result refresh interval"
                className="h-9 rounded-md border bg-background px-2 text-foreground"
                value={refreshInterval}
                onChange={(event) => setRefreshInterval(event.target.value as "5" | "10" | "never")}
              >
                <option value="5">Every 5 seconds</option>
                <option value="10">Every 10 seconds</option>
                <option value="never">Never</option>
              </select>
            </label>
          </CardHeader>
          <CardContent>
            {runs.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading runs…</p>
            ) : (
              <div className="overflow-x-auto pb-2">
                <table
                  className="table-fixed text-left text-sm"
                  style={{ width: runTableWidth }}
                >
                  <colgroup>
                    <col style={{ width: runColumnWidths.runId }} />
                    <col style={{ width: runColumnWidths.candidate }} />
                    <col style={{ width: runColumnWidths.status }} />
                    <col style={{ width: runColumnWidths.started }} />
                    <col style={{ width: runColumnWidths.duration }} />
                    <col style={{ width: runColumnWidths.progress }} />
                    <col style={{ width: runColumnWidths.failureReason }} />
                  </colgroup>
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <ResizableRunColumnHeader
                        column="runId"
                        onResizeBy={resizeRunColumn}
                        onResizeStart={startRunColumnResize}
                        width={runColumnWidths.runId}
                      >
                        Run ID
                      </ResizableRunColumnHeader>
                      <ResizableRunColumnHeader
                        column="candidate"
                        onResizeBy={resizeRunColumn}
                        onResizeStart={startRunColumnResize}
                        width={runColumnWidths.candidate}
                      >
                        Candidate
                      </ResizableRunColumnHeader>
                      <ResizableRunColumnHeader
                        column="status"
                        onResizeBy={resizeRunColumn}
                        onResizeStart={startRunColumnResize}
                        width={runColumnWidths.status}
                      >
                        Status
                      </ResizableRunColumnHeader>
                      <ResizableRunColumnHeader
                        column="started"
                        onResizeBy={resizeRunColumn}
                        onResizeStart={startRunColumnResize}
                        width={runColumnWidths.started}
                      >
                        Started
                      </ResizableRunColumnHeader>
                      <ResizableRunColumnHeader
                        column="duration"
                        onResizeBy={resizeRunColumn}
                        onResizeStart={startRunColumnResize}
                        width={runColumnWidths.duration}
                      >
                        Duration
                      </ResizableRunColumnHeader>
                      <ResizableRunColumnHeader
                        column="progress"
                        onResizeBy={resizeRunColumn}
                        onResizeStart={startRunColumnResize}
                        width={runColumnWidths.progress}
                      >
                        Progress
                      </ResizableRunColumnHeader>
                      <ResizableRunColumnHeader
                        column="failureReason"
                        onResizeBy={resizeRunColumn}
                        onResizeStart={startRunColumnResize}
                        width={runColumnWidths.failureReason}
                      >
                        Failure reason
                      </ResizableRunColumnHeader>
                    </tr>
                  </thead>
                  <tbody>
                    {(runs.data ?? []).map((item) => (
                      <tr key={item.run_id} className="border-b align-top">
                        <td className="break-all px-2 py-3 font-mono text-xs">
                          {item.run_id}
                        </td>
                        <td className="break-all px-2 py-3 font-mono text-xs">
                          {item.candidate_id}
                        </td>
                        <td className="px-2 py-3">
                          <ExperimentStatusBadge status={item.status} />
                        </td>
                        <td className="px-2 py-3 text-xs">
                          {item.started_at
                            ? new Date(item.started_at).toLocaleString()
                            : "—"}
                        </td>
                        <td className="px-2 py-3 text-xs">
                          {item.started_at && item.completed_at
                            ? `${Math.round(
                                (new Date(item.completed_at).getTime() -
                                  new Date(item.started_at).getTime()) /
                                  1000,
                              )}s`
                            : "—"}
                        </td>
                        <td className="px-2 py-3 text-xs text-muted-foreground">
                          {item.total_item_count
                            ? `${item.completed_item_count}/${item.total_item_count} executed · ${item.evaluated_item_count} evaluated`
                            : "—"}
                        </td>
                        <td className="break-words px-2 py-3 text-xs text-muted-foreground">
                          {item.failure_reason ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-center justify-between gap-4">
            <div>
              <CardTitle>Item Evaluation Results</CardTitle>
              <CardDescription>
                Completed scores are retained and visible even when a run fails or is cancelled.
              </CardDescription>
            </div>
            {(runs.data?.length ?? 0) > 1 && (
              <select
                aria-label="Evaluation run results"
                className="h-9 max-w-64 rounded-md border bg-background px-2 text-sm text-foreground"
                value={activeResultRunId}
                onChange={(event) => {
                  setSelectedRunId(event.target.value);
                  setEvaluationPage(1);
                }}
              >
                {(runs.data ?? []).map((run) => (
                  <option key={run.run_id} value={run.run_id}>
                    {run.candidate_id} · {run.status}
                  </option>
                ))}
              </select>
            )}
          </CardHeader>
          <CardContent>
            {runEvaluations.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading item results…</p>
            ) : !activeResultRunId ? (
              <p className="text-sm text-muted-foreground">Start a run to collect item-level evaluation results.</p>
            ) : !evaluationResults || evaluationResults.items.length === 0 ? (
              <p className="text-sm text-muted-foreground">No item evaluations have completed for this run yet.</p>
            ) : (
              <>
                <div className="overflow-x-auto rounded-lg border border-border/70 bg-background">
                  <table className="w-full min-w-[1080px] table-fixed text-left text-sm">
                    <colgroup>
                      <col className="w-[12%]" />
                      <col className="w-[16%]" />
                      <col className="w-[14%]" />
                      <col className="w-[40%]" />
                      <col className="w-[18%]" />
                    </colgroup>
                    <thead className="bg-muted/40">
                      <tr className="border-b border-border/70 text-muted-foreground">
                        <th className="px-4 py-3 text-xs font-medium whitespace-nowrap" scope="col">Item</th>
                        <th className="px-4 py-3 text-xs font-medium whitespace-nowrap" scope="col">Evaluator</th>
                        <th className="px-4 py-3 text-xs font-medium whitespace-nowrap" scope="col">Model latency</th>
                        <th className="px-4 py-3 text-xs font-medium whitespace-nowrap" scope="col">Scores</th>
                        <th className="px-4 py-3 text-xs font-medium whitespace-nowrap" scope="col">Completed</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/70">
                      {evaluationResults.items.map((item) => (
                        <tr key={item.evaluation_id} className="align-top transition-colors hover:bg-muted/30">
                          <td className="px-4 py-3 font-mono text-xs whitespace-nowrap">{item.execution_id.split(":").slice(-2).join(":")}</td>
                          <td className="px-4 py-3 font-medium text-foreground">{item.evaluator_type}</td>
                          <td className="px-4 py-3 whitespace-nowrap text-xs tabular-nums text-muted-foreground">
                            {item.model_latency_ms == null ? "—" : `${item.model_latency_ms} ms`}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex flex-wrap gap-1.5">
                            {item.metrics.map((metric) => (
                              <span
                                key={metric.name}
                                className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-xs tabular-nums text-foreground/85"
                                title={metric.name}
                              >
                                <span className="text-muted-foreground">{formatEvaluationMetricLabel(metric.name)}</span>
                                <span className="font-medium">{metric.score.toFixed(3)}</span>
                              </span>
                            ))}
                            </div>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-xs tabular-nums text-muted-foreground">{new Date(item.created_at).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
                  <span>
                    Showing {((evaluationResults.page - 1) * evaluationResults.page_size) + 1}–{Math.min(evaluationResults.page * evaluationResults.page_size, evaluationResults.total_items)} of {evaluationResults.total_items}
                  </span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" disabled={evaluationPage === 1} onClick={() => setEvaluationPage((current) => current - 1)}>Previous</Button>
                    <Button variant="outline" size="sm" disabled={evaluationPage * evaluationResults.page_size >= evaluationResults.total_items} onClick={() => setEvaluationPage((current) => current + 1)}>Next</Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
        </div>
      )}

      {tab === "Leaderboard" && (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Latest Leaderboard</CardTitle>
            {leaderboard.data && (
              <Button asChild variant="outline" size="sm">
                <Link
                  href={`/graph?entityType=Leaderboard&entityId=${encodeURIComponent(
                    leaderboard.data.leaderboard_id,
                  )}&depth=2&awaitProjection=true`}
                >
                  View in Ontology
                </Link>
              </Button>
            )}
          </CardHeader>
          <CardContent>
            {leaderboard.isLoading ? (
              <p className="text-sm text-muted-foreground">
                Loading leaderboard…
              </p>
            ) : leaderboard.isError || !leaderboard.data ? (
              <p className="text-sm text-muted-foreground">
                No leaderboard is available yet. Complete eligible evaluation
                runs first.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="p-2">Rank</th>
                      <th>Candidate</th>
                      <th>Ranking Value</th>
                      <th>Latency</th>
                      <th>Cost</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leaderboard.data.entries.map((item) => (
                      <tr key={item.candidate_id} className="border-b">
                        <td className="p-2">{item.rank}</td>
                        <td>{item.candidate_id}</td>
                        <td>{formatRankingValue(item.overall_score)}</td>
                        <td>{item.latency ?? "—"}</td>
                        <td>{item.cost ?? "—"}</td>
                        <td>{item.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-4 text-xs text-muted-foreground">
                  {leaderboard.data.entries.length >= 2
                    ? "A recommendation does not deploy or promote the candidate."
                    : "One candidate is an observation, not a comparison or recommendation. Ranking values are not percentages unless the selected strategy explicitly defines one."}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {tab === "Comparison" && (
        <ComparisonPanel
          candidates={candidates.data ?? []}
          baselineCandidateId={baselineCandidateId}
          comparisonCandidateId={comparisonCandidateId}
          onBaselineChange={setBaselineCandidateId}
          onComparisonChange={setComparisonCandidateId}
          comparison={comparison.data}
          isLoading={comparison.isLoading}
          isError={comparison.isError}
        />
      )}

      {tab !== "Overview" &&
        tab !== "Candidates" &&
        tab !== "Comparison" &&
        tab !== "Leaderboard" && (
          <Card>
            <CardContent className="p-8 text-sm text-muted-foreground">
              This view becomes available as evaluation run data is returned by
              the backend.
            </CardContent>
          </Card>
        )}
    </div>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  description,
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  description: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-primary/10 p-2 text-primary">
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {label}
            </p>
            <p className="mt-1 text-2xl font-semibold">{value}</p>
            <p className="mt-1 truncate text-xs text-muted-foreground">
              {description}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function CandidateCard({ candidate }: { candidate: Candidate }) {
  const runtimeParameters = candidate.runtime_parameters ?? {};
  const metadata = candidate.metadata ?? {};

  return (
    <div className="rounded-lg border bg-muted/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="break-words font-semibold">
            {candidate.candidate_name}
          </h3>
          <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
            {candidate.candidate_id}
          </p>
        </div>
        <span className="rounded-full border px-2 py-1 text-xs text-muted-foreground">
          {candidate.provider_name}
        </span>
      </div>

      <div className="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        <CandidateField label="Candidate ID" value={candidate.candidate_id} />
        <CandidateField label="Experiment ID" value={candidate.experiment_id} />
        <CandidateField
          label="Created"
          value={new Date(candidate.created_at).toLocaleString()}
        />
      </div>

      <div className="mt-5 grid gap-4 border-t pt-4 sm:grid-cols-3">
        <AssetReference
          label="Prompt"
          id={candidate.prompt_id}
          version={candidate.prompt_version}
        />
        <AssetReference
          label="Model"
          id={candidate.model_id}
          version={candidate.model_version}
        />
        <AssetReference
          label="Dataset"
          id={candidate.dataset_id}
          version={candidate.dataset_version}
        />
      </div>

      {candidate.runtime_connection_id ? (
        <div className="mt-5 border-t pt-4">
          <CandidateField
            label="Runtime connection"
            value={candidate.runtime_connection_id}
          />
        </div>
      ) : null}

      <div className="mt-5 border-t pt-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Runtime parameters
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <CandidateField
            label="Temperature"
            value={formatCandidateValue(runtimeParameters.temperature)}
          />
          <CandidateField
            label="Top P"
            value={formatCandidateValue(runtimeParameters.top_p)}
          />
          <CandidateField
            label="Max tokens"
            value={formatCandidateValue(runtimeParameters.max_tokens)}
          />
        </div>
      </div>

      <div className="mt-5 border-t pt-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Metadata
        </p>
        {Object.keys(metadata).length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">No metadata</p>
        ) : (
          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs leading-5 [overflow-wrap:anywhere]">
            {JSON.stringify(metadata, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

function ComparisonPanel({
  candidates,
  baselineCandidateId,
  comparisonCandidateId,
  onBaselineChange,
  onComparisonChange,
  comparison,
  isLoading,
  isError,
}: {
  candidates: Candidate[];
  baselineCandidateId: string;
  comparisonCandidateId: string;
  onBaselineChange: (value: string) => void;
  onComparisonChange: (value: string) => void;
  comparison?: CandidateComparison;
  isLoading: boolean;
  isError: boolean;
}) {
  const ready =
    Boolean(baselineCandidateId) &&
    Boolean(comparisonCandidateId) &&
    baselineCandidateId !== comparisonCandidateId;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Comparison</CardTitle>
          <CardDescription>
            Compare governed configuration and the latest completed evaluation
            metrics for two candidates.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <CandidateSelect
            label="Baseline Candidate"
            value={baselineCandidateId}
            candidates={candidates}
            onChange={onBaselineChange}
          />
          <CandidateSelect
            label="Comparison Candidate"
            value={comparisonCandidateId}
            candidates={candidates}
            onChange={onComparisonChange}
          />
        </CardContent>
      </Card>

      {!ready ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Select two different candidates to enable comparison.
          </CardContent>
        </Card>
      ) : isLoading ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Loading comparison…
          </CardContent>
        </Card>
      ) : isError || !comparison ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Comparison is available after both candidates have completed an
            evaluation run.
          </CardContent>
        </Card>
      ) : (
        <>
          <ConfigurationComparison
            baseline={comparison.baseline_candidate}
            comparison={comparison.comparison_candidate}
          />
          <MetricComparisonTable metrics={comparison.metric_comparisons} />
        </>
      )}
    </div>
  );
}

function CandidateSelect({
  label,
  value,
  candidates,
  onChange,
}: {
  label: string;
  value: string;
  candidates: Candidate[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="font-medium">{label}</span>
      <select
        className="h-10 rounded-md border bg-background px-3"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={candidates.length < 2}
      >
        <option value="">
          {candidates.length < 2
            ? "At least two candidates required"
            : "Select a candidate"}
        </option>
        {candidates.map((candidate) => (
          <option key={candidate.candidate_id} value={candidate.candidate_id}>
            {candidate.candidate_name} · {candidate.candidate_id}
          </option>
        ))}
      </select>
    </label>
  );
}

function ConfigurationComparison({
  baseline,
  comparison,
}: {
  baseline: Candidate;
  comparison: Candidate;
}) {
  const rows: [string, string, string][] = [
    [
      "Prompt",
      `${baseline.prompt_id} · ${baseline.prompt_version}`,
      `${comparison.prompt_id} · ${comparison.prompt_version}`,
    ],
    [
      "Model",
      `${baseline.model_id} · ${baseline.model_version}`,
      `${comparison.model_id} · ${comparison.model_version}`,
    ],
    [
      "Dataset",
      `${baseline.dataset_id} · ${baseline.dataset_version}`,
      `${comparison.dataset_id} · ${comparison.dataset_version}`,
    ],
    ["Evaluation provider", baseline.provider_name, comparison.provider_name],
    [
      "Temperature",
      formatCandidateValue(baseline.runtime_parameters.temperature),
      formatCandidateValue(comparison.runtime_parameters.temperature),
    ],
    [
      "Top P",
      formatCandidateValue(baseline.runtime_parameters.top_p),
      formatCandidateValue(comparison.runtime_parameters.top_p),
    ],
    [
      "Max tokens",
      formatCandidateValue(baseline.runtime_parameters.max_tokens),
      formatCandidateValue(comparison.runtime_parameters.max_tokens),
    ],
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Configuration comparison</CardTitle>
        <CardDescription>Differing values are highlighted.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="p-3 font-medium">Field</th>
                <th className="p-3 font-medium">Baseline</th>
                <th className="p-3 font-medium">Comparison</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([label, baselineValue, comparisonValue]) => {
                const different = baselineValue !== comparisonValue;
                return (
                  <tr
                    key={label}
                    className={different ? "border-b bg-muted/50" : "border-b"}
                  >
                    <td className="p-3 font-medium">{label}</td>
                    <td className="max-w-[320px] whitespace-normal break-words p-3">
                      {baselineValue}
                    </td>
                    <td className="max-w-[320px] whitespace-normal break-words p-3">
                      {comparisonValue}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function MetricComparisonTable({ metrics }: { metrics: MetricComparison[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Metric comparison</CardTitle>
        <CardDescription>
          Only metrics returned by the evaluation backend are shown.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {metrics.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No metrics were returned for these evaluation runs.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="p-3 font-medium">Metric</th>
                  <th className="p-3 text-right font-medium">Baseline</th>
                  <th className="p-3 text-right font-medium">Comparison</th>
                  <th className="p-3 text-right font-medium">Delta</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((metric) => (
                  <tr key={metric.metric_name} className="border-b">
                    <td className="p-3 font-medium">
                      {formatMetricName(metric.metric_name)}
                    </td>
                    <td className="p-3 text-right">
                      {formatMetricValue(metric.baseline_value)}
                    </td>
                    <td className="p-3 text-right">
                      {formatMetricValue(metric.candidate_value)}
                    </td>
                    <td className="p-3 text-right font-medium">
                      <MetricDelta metric={metric} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function formatMetricName(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatMetricValue(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "—"
    : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function formatRankingValue(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function MetricDelta({ metric }: { metric: MetricComparison }) {
  const tone = metricDeltaTone(metric);
  const value = metric.score_difference;
  const displayValue =
    value === null || value === undefined
      ? "—"
      : `${value > 0 ? "+" : ""}${formatMetricValue(value)}`;
  const label =
    tone === "positive"
      ? "Improved"
      : tone === "negative"
        ? "Worsened"
        : "No directional change";

  return (
    <span
      className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${
        tone === "positive"
          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : tone === "negative"
            ? "bg-red-500/10 text-red-700 dark:text-red-300"
            : "bg-muted text-muted-foreground"
      }`}
      title={`${label}: ${displayValue}`}
    >
      {displayValue}
    </span>
  );
}

function metricDeltaTone(
  metric: MetricComparison,
): "positive" | "negative" | "neutral" {
  const delta = metric.score_difference;
  if (delta === null || delta === undefined || delta === 0) {
    return "neutral";
  }

  const metricName = metric.metric_name.toLowerCase();
  const lowerIsBetter = ["cost", "latency", "hallucination_score"].some(
    (name) => metricName === name,
  );
  const higherIsBetter = [
    "overall_score",
    "groundedness",
    "answer_relevance",
  ].some((name) => metricName === name);

  if (!lowerIsBetter && !higherIsBetter) {
    return "neutral";
  }

  const improved = lowerIsBetter ? delta < 0 : delta > 0;
  return improved ? "positive" : "negative";
}

function AssetReference({
  label,
  id,
  version,
}: {
  label: string;
  id: string;
  version: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 break-all font-mono text-xs">{id}</p>
      <p className="mt-1 text-sm font-medium">Version {version}</p>
    </div>
  );
}

function CandidateField({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-sm font-medium">{value}</p>
    </div>
  );
}

function formatCandidateValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function DetailItem({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <div className="mt-1 break-words text-sm font-medium">{value}</div>
    </div>
  );
}

function AssetSelect({
  label,
  value,
  loading,
  options,
  emptyOptionLabel,
  onChange,
}: {
  label: string;
  value: string;
  loading: boolean;
  options: { value: string; label: string }[];
  emptyOptionLabel?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <select
        className="h-9 rounded-md border bg-background px-3"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={loading || options.length === 0}
      >
        <option value="">
          {loading
            ? "Loading…"
            : options.length === 0
              ? emptyOptionLabel ?? "No governed assets available"
              : "Select a version"}
        </option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function runtimeProviderKey(provider: string): string {
  const normalized = provider
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  if (normalized.startsWith("custom_")) {
    return "custom";
  }
  const aliases: Record<string, string> = {
      open_ai: "openai",
      anthropic_ai: "anthropic",
      openai_compatible: "custom",
      other: "custom",
  };
  return aliases[normalized] ?? normalized;
}
