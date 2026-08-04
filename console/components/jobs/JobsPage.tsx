"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  BriefcaseBusiness,
  CirclePlay,
  ClipboardList,
  Clock3,
  LoaderCircle,
  RotateCcw,
  Search,
  Send,
  Square,
} from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  cancelJob,
  getJob,
  getJobResult,
  getJobs,
  retryJob,
  submitJob,
} from "@/lib/api/jobs";
import { KavachApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils/cn";
import type { Job, JobStatus, JobType, JsonObject } from "@/types/job";

const JOB_TYPES: JobType[] = [
  "EVALUATION",
  "EXPERIMENT",
  "REPLAY",
  "DRIFT_ANALYSIS",
];
const JOB_STATUSES: JobStatus[] = [
  "QUEUED",
  "RUNNING",
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
];
const PAGE_SIZE_OPTIONS = [10, 25, 50];
const JOB_FETCH_LIMIT = 100;
const AUTO_REFRESH_OPTIONS = [
  { label: "Off", value: 0 },
  { label: "5s", value: 5_000 },
  { label: "10s", value: 10_000 },
  { label: "30s", value: 30_000 },
];

type JobFilters = {
  status: string;
  jobType: string;
};

const EMPTY_FILTERS: JobFilters = {
  status: "",
  jobType: "",
};

function filtersFromSearchParams(search: ReturnType<typeof useSearchParams>): JobFilters {
  const status = search.get("status") ?? "";
  const jobType = search.get("job_type") ?? "";
  return {
    status: JOB_STATUSES.includes(status as JobStatus) ? status : "",
    jobType: JOB_TYPES.includes(jobType as JobType) ? jobType : "",
  };
}

function setOrDelete(params: URLSearchParams, key: string, value: string) {
  if (value) params.set(key, value);
  else params.delete(key);
}

type SubmitState = {
  jobType: JobType;
  inputRefsJson: string;
  idempotencyKey: string;
  submittedBy: string;
  maxAttempts: string;
};

export function JobsPage() {
  const router = useRouter();
  const search = useSearchParams();
  const queryClient = useQueryClient();
  const urlFilters = useMemo(() => filtersFromSearchParams(search), [search]);
  const [filterInput, setFilterInput] = useState<JobFilters>(urlFilters);
  const [filters, setFilters] = useState<JobFilters>(urlFilters);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [refreshIntervalMs, setRefreshIntervalMs] = useState(5_000);
  const [submitState, setSubmitState] = useState<SubmitState>({
    jobType: "EVALUATION",
    inputRefsJson: JSON.stringify(
      {
        evaluation_id: "eval-1",
        dataset_id: "dataset-1",
      },
      null,
      2,
    ),
    idempotencyKey: "studio-job-1",
    submittedBy: "studio-admin",
    maxAttempts: "3",
  });
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    setFilterInput(urlFilters);
    setFilters(urlFilters);
    setPageIndex(0);
  }, [urlFilters]);

  const jobsQuery = useQuery({
    queryKey: ["jobs", filters],
    queryFn: () =>
      getJobs({
        status: filters.status,
        job_type: filters.jobType,
        limit: JOB_FETCH_LIMIT,
      }),
    refetchInterval: refreshIntervalMs || false,
  });
  const selectedJobQuery = useQuery({
    queryKey: ["job", selectedJobId],
    queryFn: () => getJob(selectedJobId ?? ""),
    enabled: selectedJobId !== null,
    refetchInterval: refreshIntervalMs || false,
  });
  const selectedResultQuery = useQuery({
    queryKey: ["job-result", selectedJobId],
    queryFn: () => getJobResult(selectedJobId ?? ""),
    enabled: selectedJobId !== null,
    refetchInterval: refreshIntervalMs || false,
  });
  const submitMutation = useMutation({
    mutationFn: submitJob,
    onSuccess: async (job) => {
      setSelectedJobId(job.jobId);
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["job", job.jobId] });
    },
  });
  const cancelMutation = useMutation({
    mutationFn: cancelJob,
    onSuccess: async (job) => {
      setSelectedJobId(job.jobId);
      await invalidateJobQueries(queryClient, job.jobId);
    },
  });
  const retryMutation = useMutation({
    mutationFn: retryJob,
    onSuccess: async (job) => {
      setSelectedJobId(job.jobId);
      await invalidateJobQueries(queryClient, job.jobId);
    },
  });

  const jobs = useMemo(
    () => sortedJobs(jobsQuery.data ?? []),
    [jobsQuery.data],
  );
  const stats = jobStats(jobs);
  const totalPages = Math.max(1, Math.ceil(jobs.length / pageSize));
  const currentPage = Math.min(pageIndex, totalPages - 1);
  const pagedJobs = jobs.slice(
    currentPage * pageSize,
    currentPage * pageSize + pageSize,
  );
  const selectedJob =
    selectedJobQuery.data ??
    jobs.find((job) => job.jobId === selectedJobId) ??
    null;

  function handleFiltersSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters(filterInput);
    setPageIndex(0);
    replaceFilterUrl(filterInput);
  }

  function resetFilters() {
    setFilterInput(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
    setPageIndex(0);
    replaceFilterUrl(EMPTY_FILTERS);
  }

  function replaceFilterUrl(next: JobFilters) {
    const params = new URLSearchParams(search.toString());
    setOrDelete(params, "status", next.status);
    setOrDelete(params, "job_type", next.jobType);
    router.replace(`/jobs${params.size ? `?${params}` : ""}`);
  }

  function handlePageSizeChange(value: string) {
    setPageSize(Number(value));
    setPageIndex(0);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);
    try {
      const maxAttempts = Number(submitState.maxAttempts);
      if (!Number.isInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > 10) {
        throw new Error("Attempts must be a whole number from 1 to 10.");
      }
      if (!submitState.idempotencyKey.trim()) {
        throw new Error("Idempotency key is required.");
      }
      if (!submitState.submittedBy.trim()) {
        throw new Error("Submitted by is required.");
      }
      submitMutation.mutate({
        job_type: submitState.jobType,
        input_refs: parseInputRefs(submitState.inputRefsJson),
        idempotency_key: submitState.idempotencyKey.trim(),
        submitted_by: submitState.submittedBy.trim(),
        max_attempts: maxAttempts,
      });
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Job submission is invalid.",
      );
    }
  }

  return (
    <div className="h-[calc(100vh-3.5rem)] overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-5 px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <BriefcaseBusiness className="h-5 w-5 text-primary" />
              <h1 className="text-2xl font-semibold tracking-normal">Jobs</h1>
            </div>
            <p className="mt-1 max-w-[760px] text-sm text-muted-foreground">
              Governance job runs, queue state, attempts, inputs and results.
            </p>
          </div>
          <Badge variant="outline" className="bg-card">
            Jobs Control Plane
          </Badge>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <JobSummaryStat
            label="Needs attention"
            value={stats.QUEUED + stats.FAILED}
            detail={`${stats.QUEUED} queued · ${stats.FAILED} failed`}
            tone="warning"
          />
          <JobSummaryStat
            label="Running"
            value={stats.RUNNING}
            detail="Currently executing"
            tone="progress"
          />
          <JobSummaryStat
            label="Completed"
            value={stats.SUCCEEDED}
            detail={`${stats.CANCELLED} cancelled`}
            tone="success"
          />
        </div>

        <div className="grid gap-5 xl:grid-cols-[1fr_380px]">
          <div className="space-y-5">
            <Card>
              <CardHeader className="gap-4 pb-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <CardTitle className="flex items-center gap-2">
                    <ClipboardList className="h-4 w-4 text-primary" />
                    Runs
                  </CardTitle>
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <label className="flex items-center gap-2">
                      <span className="text-xs font-medium uppercase">
                        Refresh
                      </span>
                      <select
                        value={refreshIntervalMs}
                        onChange={(event) =>
                          setRefreshIntervalMs(Number(event.target.value))
                        }
                        className="h-8 rounded-md border border-input bg-background px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        aria-label="Auto-refresh interval"
                      >
                        {AUTO_REFRESH_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <span>
                      Page {currentPage + 1} of {totalPages}
                    </span>
                    <label className="flex items-center gap-2">
                      <span className="text-xs font-medium uppercase">Rows</span>
                      <select
                        value={pageSize}
                        onChange={(event) =>
                          handlePageSizeChange(event.target.value)
                        }
                        className="h-8 rounded-md border border-input bg-background px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {PAGE_SIZE_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                </div>
                <form className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]" onSubmit={handleFiltersSubmit}>
                  <CompactSelect
                    ariaLabel="Filter by status"
                    value={filterInput.status}
                    onChange={(status) => setFilterInput({ ...filterInput, status })}
                    options={JOB_STATUSES}
                    placeholder="Any status"
                  />
                  <CompactSelect
                    ariaLabel="Filter by type"
                    value={filterInput.jobType}
                    onChange={(jobType) => setFilterInput({ ...filterInput, jobType })}
                    options={JOB_TYPES}
                    placeholder="Any type"
                  />
                  <Button type="submit" variant="outline" size="sm">
                    <Search className="h-4 w-4" />
                    Apply
                  </Button>
                  <Button type="button" variant="ghost" size="sm" onClick={resetFilters}>
                    Reset
                  </Button>
                </form>
              </CardHeader>
              <CardContent>
                {jobsQuery.isLoading ? (
                  <StatePanel label="Loading jobs..." />
                ) : jobsQuery.isError ? (
                  <ErrorPanel error={jobsQuery.error} />
                ) : jobs.length ? (
                  <>
                    <div className="divide-y rounded-md border">
                      <div className="hidden gap-3 bg-muted/30 px-4 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground lg:grid lg:grid-cols-[1.1fr_130px_110px_110px_150px_36px]">
                        <span>Run</span>
                        <span>Type</span>
                        <span>Attempts</span>
                        <span>Submitter</span>
                        <span>Updated</span>
                        <span className="sr-only">Open</span>
                      </div>
                      {pagedJobs.map((job) => (
                        <JobRow
                          key={job.jobId}
                          job={job}
                          selected={job.jobId === selectedJobId}
                          onSelect={() => setSelectedJobId(job.jobId)}
                        />
                      ))}
                    </div>
                    <div className="mt-4 flex items-center justify-between gap-3">
                      <div className="text-sm text-muted-foreground">
                        Showing {pagedJobs.length} of {jobs.length} runs
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          disabled={currentPage === 0}
                          onClick={() =>
                            setPageIndex((value) => Math.max(0, value - 1))
                          }
                        >
                          Previous
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          disabled={currentPage >= totalPages - 1}
                          onClick={() => setPageIndex((value) => value + 1)}
                        >
                          Next
                          <ArrowRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </>
                ) : (
                  <EmptyPanel />
                )}
              </CardContent>
            </Card>
          </div>

          <div className="space-y-5">
            <JobDetailPanel
              job={selectedJob}
              resultError={selectedResultQuery.error}
              result={selectedResultQuery.data ?? null}
              loading={selectedJobQuery.isLoading}
              error={selectedJobQuery.error}
              onCancel={(jobId) => cancelMutation.mutate(jobId)}
              onRetry={(jobId) => retryMutation.mutate(jobId)}
              pending={
                cancelMutation.isPending ||
                retryMutation.isPending ||
                selectedResultQuery.isFetching
              }
              mutationError={cancelMutation.error ?? retryMutation.error}
            />
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2">
                  <Send className="h-4 w-4 text-primary" />
                  Submit Job
                </CardTitle>
              </CardHeader>
              <CardContent>
                <form className="space-y-3" onSubmit={handleSubmit}>
                  <SelectBox
                    label="Type"
                    value={submitState.jobType}
                    onChange={(jobType) =>
                      setSubmitState({
                        ...submitState,
                        jobType: jobType as JobType,
                      })
                    }
                    options={JOB_TYPES}
                  />
                  <TextField
                    label="Idempotency Key"
                    value={submitState.idempotencyKey}
                    onChange={(idempotencyKey) =>
                      setSubmitState({ ...submitState, idempotencyKey })
                    }
                  />
                  <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
                    <TextField
                      label="Submitted By"
                      value={submitState.submittedBy}
                      onChange={(submittedBy) =>
                        setSubmitState({ ...submitState, submittedBy })
                      }
                    />
                    <TextField
                      label="Attempts"
                      value={submitState.maxAttempts}
                      onChange={(maxAttempts) =>
                        setSubmitState({ ...submitState, maxAttempts })
                      }
                    />
                  </div>
                  <div>
                    <LabelText>Input Refs</LabelText>
                    <textarea
                      value={submitState.inputRefsJson}
                      onChange={(event) =>
                        setSubmitState({
                          ...submitState,
                          inputRefsJson: event.target.value,
                        })
                      }
                      rows={7}
                      className={textareaClassName}
                    />
                  </div>
                  {submitError ? <InlineError message={submitError} /> : null}
                  <MutationError error={submitMutation.error} />
                  <Button type="submit" disabled={submitMutation.isPending}>
                    <Send className="h-4 w-4" />
                    Submit
                  </Button>
                </form>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

function JobSummaryStat({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: number;
  detail: string;
  tone: "warning" | "progress" | "success";
}) {
  const iconClassName = {
    warning: "bg-[#ffd60a] text-[#1f2328]",
    progress: "border-primary/30 bg-primary/10 text-primary",
    success: "bg-[#32d74b] text-[#1f2328]",
  }[tone];
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-4">
        <div>
          <div className="text-xs font-semibold uppercase text-muted-foreground">
            {label}
          </div>
          <div className="mt-1 text-2xl font-semibold">{value}</div>
          <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
        </div>
        <span className={cn("flex h-9 w-9 items-center justify-center rounded-md border border-transparent", iconClassName)}>
          {tone === "warning" ? <Clock3 className="h-4 w-4" /> : tone === "progress" ? <LoaderCircle className="h-4 w-4" /> : <CirclePlay className="h-4 w-4" />}
        </span>
      </CardContent>
    </Card>
  );
}

function JobRow({
  job,
  selected,
  onSelect,
}: {
  job: Job;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "grid w-full gap-3 px-4 py-3 text-left hover:bg-accent/55 lg:grid-cols-[1.1fr_130px_110px_110px_150px_36px]",
        selected && "bg-accent/70",
      )}
    >
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="truncate font-mono text-sm font-semibold">
            {job.jobId}
          </span>
          <StatusBadge status={job.status} />
        </div>
        <div className="mt-1 truncate text-sm text-muted-foreground">
          {job.idempotencyKey}
        </div>
      </div>
      <FieldBlock compact label="Type" value={job.jobType} />
      <FieldBlock compact label="Attempts" value={`${job.attemptCount}/${job.maxAttempts}`} />
      <FieldBlock compact label="Submitter" value={job.submittedBy} />
      <FieldBlock compact label="Updated" value={formatDate(job.updatedAt)} />
      <div className="flex items-center justify-end">
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
      </div>
    </button>
  );
}

function JobDetailPanel({
  job,
  result,
  resultError,
  loading,
  error,
  onCancel,
  onRetry,
  pending,
  mutationError,
}: {
  job: Job | null;
  result: { resultRef: string | null; failureReason: string | null } | null;
  resultError: unknown;
  loading: boolean;
  error: unknown;
  onCancel: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  pending: boolean;
  mutationError: unknown;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" />
          Run Details
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <StatePanel label="Loading run..." />
        ) : error ? (
          <ErrorPanel error={error} />
        ) : job ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-mono text-sm font-semibold">
                  {job.jobId}
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  {job.jobType}
                </div>
              </div>
              <StatusBadge status={job.status} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <FieldBlock label="Created" value={formatDate(job.createdAt)} />
              <FieldBlock label="Updated" value={formatDate(job.updatedAt)} />
              <FieldBlock label="Started" value={job.startedAt ? formatDate(job.startedAt) : "None"} />
              <FieldBlock label="Completed" value={job.completedAt ? formatDate(job.completedAt) : "None"} />
              <FieldBlock label="Attempts" value={`${job.attemptCount}/${job.maxAttempts}`} />
              <FieldBlock label="Submitted by" value={job.submittedBy} />
            </div>
            <FieldBlock label="Input Hash" value={job.inputHash} mono />
            <FieldBlock
              label="Result"
              value={result?.resultRef ?? job.resultRef ?? "None"}
              mono
            />
            {job.failureReason ?? result?.failureReason ? (
              <InlineError message={job.failureReason ?? result?.failureReason ?? ""} />
            ) : null}
            {resultError ? <MutationError error={resultError} /> : null}
            <MutationError error={mutationError} />
            <details className="rounded-md border bg-muted/15 px-3 py-2.5">
              <summary className="cursor-pointer text-sm font-medium">Technical details</summary>
              <div className="mt-4">
                <JsonBlock title="Input refs" value={job.inputRefs} />
              </div>
            </details>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={!canCancel(job) || pending}
                onClick={() => onCancel(job.jobId)}
              >
                <Square className="h-4 w-4" />
                Cancel
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={job.status !== "FAILED" || pending}
                onClick={() => onRetry(job.jobId)}
              >
                <RotateCcw className="h-4 w-4" />
                Retry
              </Button>
            </div>
          </div>
        ) : (
          <StatePanel label="Select a run" />
        )}
      </CardContent>
    </Card>
  );
}

function JsonBlock({
  title,
  value,
}: {
  title: string;
  value: JsonObject;
}) {
  return (
    <div>
      <LabelText>{title}</LabelText>
      <pre className="mt-1 max-h-48 overflow-auto rounded-md border bg-background p-3 text-xs leading-5">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function SelectBox({
  label,
  value,
  onChange,
  options,
  includeAny = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  includeAny?: boolean;
}) {
  return (
    <label className="block">
      <LabelText>{label}</LabelText>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {includeAny ? <option value="">Any</option> : null}
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function CompactSelect({
  value,
  onChange,
  options,
  placeholder,
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  options: string[];
  placeholder: string;
  ariaLabel: string;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      aria-label={ariaLabel}
      className="h-9 min-w-0 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <option value="">{placeholder}</option>
      {options.map((option) => <option key={option} value={option}>{option}</option>)}
    </select>
  );
}

function TextField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <LabelText>{label}</LabelText>
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1"
      />
    </label>
  );
}

function FieldBlock({
  label,
  value,
  mono = false,
  compact = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
  compact?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className={cn("text-xs font-semibold uppercase text-muted-foreground", compact && "lg:hidden")}>
        {label}
      </div>
      <div
        className={cn(
          "mt-1 truncate text-sm font-medium",
          mono && "font-mono text-xs",
        )}
        title={value}
      >
        {value}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <Badge
      variant="outline"
      className={cn("border-transparent font-semibold", statusBadgeClassName(status))}
    >
      {status}
    </Badge>
  );
}

function StatePanel({ label }: { label: string }) {
  return (
    <div className="flex min-h-[180px] items-center justify-center rounded-md border bg-card text-sm text-muted-foreground">
      {label}
    </div>
  );
}

function EmptyPanel() {
  return (
    <div className="flex min-h-[180px] flex-col items-center justify-center rounded-md border bg-card px-4 py-6 text-center">
      <BriefcaseBusiness className="h-6 w-6 text-muted-foreground" />
      <div className="mt-3 text-sm font-semibold">No jobs found</div>
    </div>
  );
}

function ErrorPanel({ error }: { error: unknown }) {
  return (
    <div className="flex min-h-[180px] items-center justify-center gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-4 text-sm text-destructive">
      <AlertCircle className="h-4 w-4" />
      {formatError(error)}
    </div>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
      {message}
    </div>
  );
}

function MutationError({ error }: { error: unknown }) {
  return error ? <InlineError message={formatError(error)} /> : null;
}

function parseInputRefs(value: string): JsonObject {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Input refs must be a JSON object.");
  }
  return parsed as JsonObject;
}

function sortedJobs(jobs: Job[]) {
  return [...jobs].sort(
    (left, right) =>
      new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime(),
  );
}

function jobStats(jobs: Job[]): Record<JobStatus, number> {
  return JOB_STATUSES.reduce(
    (stats, status) => ({
      ...stats,
      [status]: jobs.filter((job) => job.status === status).length,
    }),
    {
      QUEUED: 0,
      RUNNING: 0,
      SUCCEEDED: 0,
      FAILED: 0,
      CANCELLED: 0,
    },
  );
}

async function invalidateJobQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  jobId: string,
) {
  await queryClient.invalidateQueries({ queryKey: ["jobs"] });
  await queryClient.invalidateQueries({ queryKey: ["job", jobId] });
  await queryClient.invalidateQueries({ queryKey: ["job-result", jobId] });
}

function canCancel(job: Job) {
  return job.status === "QUEUED" || job.status === "RUNNING";
}

function statusBadgeClassName(status: JobStatus) {
  if (status === "SUCCEEDED") {
    return "bg-[#32d74b] text-[#1f2328]";
  }
  if (status === "QUEUED") {
    return "bg-[#ffd60a] text-[#1f2328]";
  }
  if (status === "RUNNING") {
    return "bg-primary text-primary-foreground";
  }
  if (status === "FAILED" || status === "CANCELLED") {
    return "bg-[#ff453a] text-[#1f2328]";
  }
  return "bg-secondary text-secondary-foreground";
}


function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-AU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatError(error: unknown) {
  if (error instanceof KavachApiError) {
    return `${error.code}: ${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unexpected error.";
}

function LabelText({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
      {children}
    </div>
  );
}

const textareaClassName =
  "mt-1 min-h-9 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
