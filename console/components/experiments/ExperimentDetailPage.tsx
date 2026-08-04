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
import { useState, type ReactNode } from "react";

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
  getCandidateComparison,
  getExperiment,
  getLeaderboard,
  listCandidates,
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
  runtime_parameters: Record<string, unknown>;
};

const INITIAL_CANDIDATE: CandidateDraft = {
  candidate_name: "",
  prompt_version: "",
  model_version: "",
  dataset_version: "",
  provider_name: "",
  provider_installation_id: "",
  runtime_parameters: {},
};

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
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [baselineCandidateId, setBaselineCandidateId] = useState("");
  const [comparisonCandidateId, setComparisonCandidateId] = useState("");

  const experiment = useQuery({
    queryKey: ["experiment", experimentId],
    queryFn: () => getExperiment(experimentId),
  });
  const candidates = useQuery({
    queryKey: ["candidates", experimentId],
    queryFn: () => listCandidates(experimentId),
    enabled: tab === "Overview" || tab === "Candidates" || tab === "Comparison",
  });
  const runs = useQuery({
    queryKey: ["runs", experimentId],
    queryFn: () => listRuns(experimentId),
    enabled: tab === "Evaluation Runs" || tab === "Overview",
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

  const add = useMutation({
    mutationFn: () => addCandidate(experimentId, candidate),
    onSuccess: async () => {
      setCandidate({ ...candidate, candidate_name: "" });
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
    mutationFn: () => runExperiment(experimentId),
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
    onError: (cause) =>
      setError(
        cause instanceof Error ? cause.message : "Unable to run experiment.",
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
    runs.data?.filter((item) => item.status === "FAILED").length ?? 0;
  const successRate = totalRuns
    ? Math.round((completedRuns / totalRuns) * 100)
    : null;
  const topEntry = leaderboard.data?.entries[0];
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
    ]);
    setRefreshing(false);
  }

  return (
    <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-5 px-6 py-5">
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
          <Button
            variant="outline"
            disabled={refreshing}
            onClick={() => void refreshExperiment()}
          >
            <RefreshCw className="h-4 w-4" />
            {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
          {experimentData.status === "DRAFT" && (
            <Button disabled={run.isPending} onClick={() => run.mutate()}>
              <Play className="h-4 w-4" />
              {run.isPending ? "Running…" : "Start Experiment"}
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
              label="Best score"
              value={topEntry ? `${Math.round(topEntry.overall_score * 100)}%` : "—"}
              description={topEntry ? `Rank 1 · ${topEntry.candidate_id}` : "No leaderboard yet"}
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
                  options={(prompts.data ?? []).map((item) => ({
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
                  options={(models.data ?? []).map((item) => ({
                    value: `${item.model_id}:${item.version}`,
                    label: `${item.provider} / ${item.model_name} · ${item.version}`,
                  }))}
                  onChange={(value) =>
                    setCandidate({ ...candidate, model_version: value })
                  }
                />
                <AssetSelect
                  label="Dataset version"
                  value={candidate.dataset_version}
                  loading={datasets.isLoading}
                  options={(datasets.data ?? []).map((item) => ({
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
                {!providerInstallations.isLoading && !(providerInstallations.data ?? []).some((item) => item.enabled) ? <p className="text-sm text-muted-foreground">Create and enable a provider installation in <Link className="text-primary underline" href="/assets/providers">Evaluation Providers</Link> before adding a candidate.</p> : null}
                <Button
                  className="w-full"
                  disabled={
                    add.isPending ||
                    !candidate.candidate_name.trim() ||
                    !candidate.prompt_version ||
                    !candidate.model_version ||
                    !candidate.dataset_version ||
                    !candidate.provider_installation_id
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
        <Card>
          <CardHeader>
            <CardTitle>Evaluation Runs</CardTitle>
          </CardHeader>
          <CardContent>
            {runs.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading runs…</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="p-2">Run ID</th>
                      <th>Candidate</th>
                      <th>Status</th>
                      <th>Started</th>
                      <th>Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(runs.data ?? []).map((item) => (
                      <tr key={item.run_id} className="border-b">
                        <td className="p-2 font-mono text-xs">{item.run_id}</td>
                        <td>{item.candidate_id}</td>
                        <td>
                          <ExperimentStatusBadge status={item.status} />
                        </td>
                        <td>
                          {item.started_at
                            ? new Date(item.started_at).toLocaleString()
                            : "—"}
                        </td>
                        <td>
                          {item.started_at && item.completed_at
                            ? `${Math.round(
                                (new Date(item.completed_at).getTime() -
                                  new Date(item.started_at).getTime()) /
                                  1000,
                              )}s`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
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
                      <th>Overall Score</th>
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
                        <td>{item.overall_score}</td>
                        <td>{item.latency ?? "—"}</td>
                        <td>{item.cost ?? "—"}</td>
                        <td>{item.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-4 text-xs text-muted-foreground">
                  A recommendation does not deploy or promote the candidate.
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
  onChange,
}: {
  label: string;
  value: string;
  loading: boolean;
  options: { value: string; label: string }[];
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
              ? "No governed assets available"
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
