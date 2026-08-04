"use client";

import Link from "next/link";
import { useInfiniteQuery, useMutation } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, ClipboardCheck, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  createReplay,
  searchReplayExecutions,
  validateReplay,
} from "@/lib/api/replays";
import type {
  ReplayConfiguration,
  ReplayExecutionSearchItem,
} from "@/types/replay";

const EXECUTION_STATUSES = ["COMPLETED", "FAILED", "CANCELLED"];

export function ReplayCreatePage() {
  const router = useRouter();
  const search = useSearchParams();
  const initialExecutionId = search.get("source_execution_id") ?? "";
  const [sourceExecutionId, setSourceExecutionId] = useState(initialExecutionId);
  const [searchText, setSearchText] = useState(initialExecutionId);
  const [debouncedSearch, setDebouncedSearch] = useState(initialExecutionId);
  const [workflowId, setWorkflowId] = useState("");
  const [executionStatus, setExecutionStatus] = useState("");
  const [createdAfter, setCreatedAfter] = useState("");
  const [createdBefore, setCreatedBefore] = useState("");
  const [replayableOnly, setReplayableOnly] = useState(true);
  const [selectedExecution, setSelectedExecution] =
    useState<ReplayExecutionSearchItem | null>(null);
  const [reason, setReason] = useState("");
  const [metadata, setMetadata] = useState("{}");
  const [configuration, setConfiguration] = useState<ReplayConfiguration | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState(1);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearch(searchText.trim()), 250);
    return () => window.clearTimeout(timeout);
  }, [searchText]);

  const executionSearch = useInfiniteQuery({
    queryKey: [
      "replay-execution-search",
      debouncedSearch,
      workflowId,
      executionStatus,
      createdAfter,
      createdBefore,
      replayableOnly,
    ],
    queryFn: ({ pageParam }) =>
      searchReplayExecutions({
        query: debouncedSearch || undefined,
        workflow_id: workflowId || undefined,
        status: executionStatus || undefined,
        created_after: createdAfter ? `${createdAfter}T00:00:00Z` : undefined,
        created_before: createdBefore ? `${createdBefore}T23:59:59Z` : undefined,
        replayable_only: replayableOnly,
        cursor: pageParam || undefined,
        limit: 10,
      }),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(
      debouncedSearch || workflowId || executionStatus || createdAfter || createdBefore,
    ),
  });
  const executionResults = useMemo(
    () => executionSearch.data?.pages.flatMap((page) => page.items) ?? [],
    [executionSearch.data],
  );
  const payload = () => ({
    source_execution_id: sourceExecutionId.trim(),
    idempotency_key: crypto.randomUUID(),
    mode: "FULL" as const,
    configuration_source: "ORIGINAL" as const,
    metadata: parseMetadata(metadata),
    reason,
  });
  const validate = useMutation({
    mutationFn: () => validateReplay(payload()),
    onSuccess: (data) => {
      const candidate = data.configuration;
      if (candidate && typeof candidate === "object") {
        setConfiguration(candidate as ReplayConfiguration);
      }
      setError(null);
      setStep(3);
    },
    onError: (cause) =>
      setError(
        cause instanceof Error ? cause.message : "Replay validation failed.",
      ),
  });
  const create = useMutation({
    mutationFn: () => createReplay(payload()),
    onSuccess: (replay) => router.push(`/replays/${replay.replay_id}`),
    onError: (cause) =>
      setError(cause instanceof Error ? cause.message : "Unable to create replay."),
  });

  function chooseExecution(execution: ReplayExecutionSearchItem) {
    setSelectedExecution(execution);
    setSourceExecutionId(execution.execution_id);
    setSearchText(execution.execution_id);
    setConfiguration(null);
    setError(null);
    setStep(1);
  }

  function validateSource() {
    setError(null);
    setConfiguration(null);
    if (!sourceExecutionId.trim()) {
      setError("Select a source execution or paste its exact ID.");
      return;
    }
    try {
      parseMetadata(metadata);
    } catch {
      setError("Metadata must be valid JSON.");
      return;
    }
    setStep(2);
    validate.mutate();
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-6 py-5">
      <Link
        href="/replays"
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Replay Management
      </Link>
      <div>
        <h1 className="text-2xl font-semibold">Create Replay</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Search only authorized historical executions, then freeze and review
          their evidence before submitting work.
        </p>
      </div>
      <ol className="grid gap-2 sm:grid-cols-4">
        {["Select execution", "Validate replayability", "Review configuration", "Create replay"].map(
          (label, index) => (
            <li
              key={label}
              className={`rounded-md border px-3 py-2 text-sm ${
                step >= index + 1
                  ? "border-primary bg-primary/5 text-foreground"
                  : "text-muted-foreground"
              }`}
            >
              <span className="mr-2 font-semibold">{index + 1}</span>
              {label}
            </li>
          ),
        )}
      </ol>
      <Card>
        <CardHeader>
          <CardTitle>1. Select historical execution</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[1fr_220px_180px]">
            <label className="block text-sm font-medium md:col-span-3">
              Search execution ID, workflow, or service
              <div className="relative mt-1">
                <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <input
                  className="h-10 w-full rounded-md border bg-background py-2 pl-9 pr-3"
                  value={searchText}
                  onChange={(event) => {
                    setSearchText(event.target.value);
                    setSourceExecutionId(event.target.value);
                    setSelectedExecution(null);
                    setConfiguration(null);
                    setStep(1);
                  }}
                  placeholder="Search the current tenant or paste an exact execution ID"
                />
              </div>
            </label>
            <label className="block text-sm font-medium">
              Workflow ID
              <input
                className="mt-1 h-10 w-full rounded-md border bg-background px-3 font-normal"
                value={workflowId}
                onChange={(event) => setWorkflowId(event.target.value)}
                placeholder="Optional"
              />
            </label>
            <label className="block text-sm font-medium">
              Execution status
              <select
                className="mt-1 h-10 w-full rounded-md border bg-background px-3 font-normal"
                value={executionStatus}
                onChange={(event) => setExecutionStatus(event.target.value)}
              >
                <option value="">All statuses</option>
                {EXECUTION_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-end gap-2 pb-2 text-sm">
              <input
                type="checkbox"
                checked={replayableOnly}
                onChange={(event) => setReplayableOnly(event.target.checked)}
              />
              Replayable only
            </label>
            <label className="block text-sm font-medium">
              Created after
              <input
                type="date"
                className="mt-1 h-10 w-full rounded-md border bg-background px-3 font-normal"
                value={createdAfter}
                onChange={(event) => setCreatedAfter(event.target.value)}
              />
            </label>
            <label className="block text-sm font-medium">
              Created before
              <input
                type="date"
                className="mt-1 h-10 w-full rounded-md border bg-background px-3 font-normal"
                value={createdBefore}
                onChange={(event) => setCreatedBefore(event.target.value)}
              />
            </label>
          </div>
          <p className="text-xs text-muted-foreground">
            Search is tenant-scoped and cursor-paginated. Pasting an exact ID
            remains available when opening from an external execution link.
          </p>
          {selectedExecution ? (
            <SelectedExecution execution={selectedExecution} />
          ) : null}
          {executionSearch.isFetching && !executionResults.length ? (
            <div className="rounded-md border p-3 text-sm text-muted-foreground">
              Searching authorized executions…
            </div>
          ) : null}
          {executionResults.length ? (
            <div className="divide-y rounded-md border">
              {executionResults.map((execution) => (
                <div
                  key={execution.execution_id}
                  className="flex flex-wrap items-center justify-between gap-3 p-3"
                >
                  <div>
                    <div className="font-medium">{execution.workflow_name}</div>
                    <div className="mt-1 font-mono text-xs text-muted-foreground">
                      {execution.execution_id}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {execution.workflow_id} · {execution.workflow_version} · {execution.execution_status}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/replay-executions/${encodeURIComponent(execution.execution_id)}`}
                      className="text-sm text-primary hover:underline"
                    >
                      View
                    </Link>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!execution.replayable}
                      onClick={() => chooseExecution(execution)}
                    >
                      Use source
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {executionSearch.hasNextPage ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={executionSearch.isFetchingNextPage}
              onClick={() => void executionSearch.fetchNextPage()}
            >
              {executionSearch.isFetchingNextPage ? "Loading…" : "Load more results"}
            </Button>
          ) : null}
          <label className="block text-sm font-medium">
            Reason
            <textarea
              className="mt-1 min-h-20 w-full rounded-md border bg-background p-3 font-normal"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Why is this replay required?"
            />
          </label>
          <label className="block text-sm font-medium">
            Metadata (optional JSON)
            <textarea
              className="mt-1 min-h-20 w-full rounded-md border bg-background p-3 font-mono text-xs font-normal"
              value={metadata}
              onChange={(event) => setMetadata(event.target.value)}
            />
          </label>
          <div className="flex justify-end">
            <Button onClick={validateSource} disabled={validate.isPending}>
              <ClipboardCheck className="h-4 w-4" />
              {validate.isPending ? "Validating…" : "Validate replayability"}
            </Button>
          </div>
        </CardContent>
      </Card>
      {error ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {configuration ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
              2–3. Replayable: frozen historical configuration
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Workflow" value={`${configuration.workflow_id} · ${configuration.workflow_version}`} />
              <Field label="Runtime adapter" value={configuration.execution_adapter} />
              <Field label="Input snapshot" value={configuration.input_snapshot_ref} />
              <Field label="State snapshot" value={configuration.state_snapshot_ref} />
              <Field label="Configuration hash" value={configuration.configuration_hash} />
            </div>
            <details>
              <summary className="cursor-pointer text-sm font-medium">
                References and runtime parameters
              </summary>
              <pre className="mt-2 overflow-auto rounded-md bg-muted p-3 text-xs">
                {JSON.stringify(
                  {
                    artifacts: configuration.artifact_refs,
                    prompts: configuration.prompt_refs,
                    models: configuration.model_refs,
                    datasets: configuration.dataset_refs,
                    policies: configuration.policy_refs,
                    runtime_parameters: configuration.runtime_parameters,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
            <div className="flex justify-end">
              <Button onClick={() => create.mutate()} disabled={create.isPending}>
                {create.isPending ? "Creating…" : "Create replay"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function SelectedExecution({ execution }: { execution: ReplayExecutionSearchItem }) {
  return (
    <div className="rounded-md border border-primary/40 bg-primary/5 p-3 text-sm">
      <div className="font-medium">Selected source: {execution.workflow_name}</div>
      <div className="mt-1 font-mono text-xs">{execution.execution_id}</div>
      <div className="mt-1 text-muted-foreground">
        {execution.workflow_version} · {execution.execution_status}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 break-all font-mono text-sm">{value}</div>
    </div>
  );
}

function parseMetadata(value: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(value || "{}");
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Metadata must be an object.");
  }
  return parsed as Record<string, unknown>;
}
