"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  BadgeInfo,
  LoaderCircle,
  Search,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getAuditDetail, getAuditPage } from "@/lib/api/audit";
import { KavachApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils/cn";
import type {
  AuditDetail,
  AuditListItem,
  AuditMetric,
} from "@/types/audit";

const PAGE_SIZE_OPTIONS = [10, 25, 50];

type AuditFilters = {
  search: string;
  status: string;
  toolName: string;
  actorId: string;
  resourceType: string;
  operationType: string;
  interrupted: string;
  dryRun: string;
};

const EMPTY_FILTERS: AuditFilters = {
  search: "",
  status: "",
  toolName: "",
  actorId: "",
  resourceType: "",
  operationType: "",
  interrupted: "",
  dryRun: "",
};

export function McpAuditPage() {
  const [filterInput, setFilterInput] = useState<AuditFilters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<AuditFilters>(EMPTY_FILTERS);
  const [selectedAuditId, setSelectedAuditId] = useState<string | null>(null);
  const [pageSize, setPageSize] = useState(10);
  const [pageIndex, setPageIndex] = useState(0);

  const auditPageQuery = useQuery({
    queryKey: ["mcp-audit-page", filters, pageIndex, pageSize],
    queryFn: () =>
      getAuditPage({
        search: filters.search,
        status: filters.status,
        tool_name: filters.toolName,
        actor_id: filters.actorId,
        resource_type: filters.resourceType,
        operation_type: filters.operationType,
        interrupted: filters.interrupted,
        dry_run: filters.dryRun,
        offset: pageIndex * pageSize,
        limit: pageSize,
        interrupted_after_seconds: 60,
      }),
  });
  const page = auditPageQuery.data;
  const records = page?.records ?? [];
  const resolvedSelectedAuditId =
    selectedAuditId && records.some((record) => record.auditId === selectedAuditId)
      ? selectedAuditId
      : (records[0]?.auditId ?? null);

  const detailQuery = useQuery({
    queryKey: ["mcp-audit-detail", resolvedSelectedAuditId],
    queryFn: () =>
      getAuditDetail(resolvedSelectedAuditId ?? "", {
        interrupted_after_seconds: 60,
      }),
    enabled: resolvedSelectedAuditId !== null,
  });
  const detail =
    detailQuery.data ??
    records.find((record) => record.auditId === resolvedSelectedAuditId) ??
    null;
  const totalPages = page ? Math.max(1, Math.ceil(page.total / page.limit)) : 1;
  const filtersOptions = page?.filters;
  const summary = auditSummary(page?.summary ?? []);

  function submitFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters(filterInput);
    setPageIndex(0);
  }

  function resetFilters() {
    setFilterInput(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
    setPageIndex(0);
  }

  function handlePageSizeChange(value: string) {
    setPageSize(Number(value));
    setPageIndex(0);
  }

  return (
    <div className="h-[calc(100vh-4rem)] overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1360px] flex-col gap-5 px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-primary" />
              <h1 className="text-2xl font-semibold tracking-normal">
                MCP Audit Ledger
              </h1>
            </div>
            <p className="mt-1 max-w-[780px] text-sm text-muted-foreground">
              Control-plane mutation evidence, linked jobs and correlation traces.
            </p>
          </div>
        </div>
        <nav
          aria-label="MCP audit views"
          className="flex w-fit rounded-md border bg-muted/30 p-1 text-sm"
        >
          <Link
            href="/audit"
            aria-current="page"
            className="flex items-center gap-2 rounded bg-primary px-3 py-2 font-semibold text-primary-foreground shadow-sm"
          >
            <ShieldCheck className="h-4 w-4" />
            MCP Write Mutations
          </Link>
          <Link
            href="/audit/invocations"
            className="flex items-center gap-2 rounded px-3 py-2 font-medium text-muted-foreground hover:bg-background hover:text-foreground"
          >
            <Workflow className="h-4 w-4" />
            All MCP Invocations
          </Link>
        </nav>

        {auditPageQuery.isLoading ? (
          <StatePanel label="Loading MCP audit..." />
        ) : auditPageQuery.isError ? (
          <ErrorPanel error={auditPageQuery.error} />
        ) : page ? (
          <>
            <div className="grid gap-3 md:grid-cols-3">
              <AuditSummaryStat
                label="Needs attention"
                value={summary.interrupted + summary.failed}
                detail={`${summary.interrupted} interrupted · ${summary.failed} failed`}
                tone={summary.failed > 0 ? "danger" : "warning"}
              />
              <AuditSummaryStat
                label="In progress"
                value={summary.started}
                detail="Audit records currently open"
                tone="progress"
              />
              <AuditSummaryStat
                label="Completed"
                value={summary.succeeded + summary.dryRun}
                detail={`${summary.succeeded} succeeded · ${summary.dryRun} dry runs`}
                tone="success"
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
              <div className="space-y-5">
                <Card>
                  <CardHeader className="gap-4 pb-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <CardTitle className="flex items-center gap-2">
                        <Workflow className="h-4 w-4 text-primary" />
                        Audit Records
                      </CardTitle>
                      <div className="flex items-center gap-3 text-sm text-muted-foreground">
                        <span>
                          Page {pageIndex + 1} of {totalPages}
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
                    <form className="space-y-3" onSubmit={submitFilters}>
                      <div className="grid gap-3 sm:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)_minmax(0,1fr)_auto_auto]">
                        <CompactSearchField
                          value={filterInput.search}
                          onChange={(search) =>
                            setFilterInput({ ...filterInput, search })
                          }
                        />
                        <CompactSelectField
                          ariaLabel="Filter by audit status"
                          placeholder="Any status"
                          value={filterInput.status}
                          options={filtersOptions?.statuses ?? []}
                          onChange={(status) =>
                            setFilterInput({ ...filterInput, status })
                          }
                        />
                        <CompactSelectField
                          ariaLabel="Filter by MCP tool"
                          placeholder="Any tool"
                          value={filterInput.toolName}
                          options={filtersOptions?.toolNames ?? []}
                          onChange={(toolName) =>
                            setFilterInput({ ...filterInput, toolName })
                          }
                        />
                        <Button type="submit" variant="outline" size="sm">
                          <Search className="h-4 w-4" />
                          Apply
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={resetFilters}
                        >
                          Reset
                        </Button>
                      </div>
                      <details className="rounded-md border bg-muted/15 px-3 py-2.5">
                        <summary className="cursor-pointer text-sm font-medium">
                          More filters
                        </summary>
                        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                          <SelectField
                            label="Actor"
                            value={filterInput.actorId}
                            options={filtersOptions?.actorIds ?? []}
                            onChange={(actorId) =>
                              setFilterInput({ ...filterInput, actorId })
                            }
                          />
                          <SelectField
                            label="Resource"
                            value={filterInput.resourceType}
                            options={filtersOptions?.resourceTypes ?? []}
                            onChange={(resourceType) =>
                              setFilterInput({ ...filterInput, resourceType })
                            }
                          />
                          <SelectField
                            label="Operation"
                            value={filterInput.operationType}
                            options={filtersOptions?.operationTypes ?? []}
                            onChange={(operationType) =>
                              setFilterInput({ ...filterInput, operationType })
                            }
                          />
                          <SelectField
                            label="Interrupted"
                            value={filterInput.interrupted}
                            options={["true", "false"]}
                            optionLabels={{ true: "Yes", false: "No" }}
                            onChange={(interrupted) =>
                              setFilterInput({ ...filterInput, interrupted })
                            }
                          />
                          <SelectField
                            label="Dry Run"
                            value={filterInput.dryRun}
                            options={["true", "false"]}
                            optionLabels={{ true: "Yes", false: "No" }}
                            onChange={(dryRun) =>
                              setFilterInput({ ...filterInput, dryRun })
                            }
                          />
                        </div>
                      </details>
                    </form>
                  </CardHeader>
                  <CardContent>
                    {records.length ? (
                      <>
                        <div className="divide-y rounded-md border">
                          <div className="hidden gap-3 bg-muted/30 px-4 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground lg:grid lg:grid-cols-[minmax(0,1.2fr)_170px_130px_120px_160px_36px]">
                            <span>Audit record</span>
                            <span>Tool</span>
                            <span>Actor</span>
                            <span>Job</span>
                            <span>Started</span>
                            <span className="sr-only">Open</span>
                          </div>
                          {records.map((record) => (
                            <AuditRow
                              key={record.auditId}
                              record={record}
                              selected={record.auditId === selectedAuditId}
                              onSelect={() => setSelectedAuditId(record.auditId)}
                            />
                          ))}
                        </div>
                        <div className="mt-4 flex items-center justify-between gap-3">
                          <div className="text-sm text-muted-foreground">
                            Showing {records.length} of {page.total} records
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              type="button"
                              variant="outline"
                              disabled={pageIndex === 0}
                              onClick={() =>
                                setPageIndex((value) => Math.max(0, value - 1))
                              }
                            >
                              Previous
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              disabled={pageIndex >= totalPages - 1}
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

              <AuditDetailPanel
                record={detail}
                loading={detailQuery.isLoading}
                error={detailQuery.error}
              />
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

function AuditSummaryStat({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: number;
  detail: string;
  tone: "warning" | "danger" | "progress" | "success";
}) {
  const iconClassName = {
    warning: "bg-[#ffd60a] text-[#1f2328]",
    danger: "bg-[#ff453a] text-[#1f2328]",
    progress: "border-primary/30 bg-primary/10 text-primary",
    success: "bg-[#32d74b] text-[#1f2328]",
  }[tone];
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 p-4">
        <div>
          <div className="text-xs font-semibold uppercase text-muted-foreground">
            {label}
          </div>
          <div className="mt-1 text-2xl font-semibold">{value}</div>
          <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
        </div>
        <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-transparent", iconClassName)}>
          {tone === "success" ? <ShieldCheck className="h-4 w-4" /> : tone === "progress" ? <LoaderCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
        </span>
      </CardContent>
    </Card>
  );
}

function AuditRow({
  record,
  selected,
  onSelect,
}: {
  record: AuditListItem;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "grid w-full gap-3 px-4 py-3 text-left hover:bg-accent/55 lg:grid-cols-[minmax(0,1.2fr)_170px_130px_120px_160px_36px]",
        selected && "bg-accent/70",
      )}
    >
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="truncate font-mono text-sm font-semibold">
            {record.auditId}
          </span>
          <AuditStatusBadge record={record} />
        </div>
        <div className="mt-1 truncate text-sm text-muted-foreground">
          {record.requestId}
        </div>
      </div>
      <FieldBlock compact label="Tool" value={record.toolName} />
      <FieldBlock compact label="Actor" value={record.actorId} />
      <FieldBlock
        compact
        label="Job"
        value={record.jobStatus ?? record.jobId ?? "None"}
      />
      <FieldBlock compact label="Started" value={formatDate(record.startedAt)} />
      <div className="flex items-center justify-end">
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
      </div>
    </button>
  );
}

function AuditDetailPanel({
  record,
  loading,
  error,
}: {
  record: AuditDetail | AuditListItem | null;
  loading: boolean;
  error: unknown;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <BadgeInfo className="h-4 w-4 text-primary" />
          Record Details
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <StatePanel label="Loading record..." />
        ) : error ? (
          <ErrorPanel error={error} />
        ) : record ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-mono text-sm font-semibold">
                  {record.auditId}
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  {"toolName" in record ? record.toolName : ""}
                </div>
              </div>
              <AuditStatusBadge record={record} />
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <FieldBlock label="Request" value={record.requestId} mono />
              <FieldBlock
                label="Correlation"
                value={record.correlationId}
                mono
              />
              <FieldBlock
                label="Started"
                value={formatDate(record.startedAt)}
              />
              <FieldBlock
                label="Completed"
                value={
                  record.completedAt ? formatDate(record.completedAt) : "None"
                }
              />
              <FieldBlock
                label="Operation"
                value={humanizeToken(record.operationType)}
              />
              <FieldBlock
                label="Resource"
                value={record.resourceId ?? record.resourceType}
              />
              <FieldBlock
                label="Actor"
                value={
                  "actorType" in record
                    ? `${record.actorId} (${record.actorType})`
                    : record.actorId
                }
              />
              <FieldBlock
                label="Duration"
                value={formatDuration(record.durationMs)}
              />
            </div>

            <div className="flex flex-wrap gap-2">
              <MiniBadge label={record.resourceType} />
              {"dryRun" in record && record.dryRun ? (
                <MiniBadge label="Dry Run" tone="warn" />
              ) : null}
              {"interrupted" in record && record.interrupted ? (
                <MiniBadge label="Interrupted" tone="warn" />
              ) : null}
              {"errorCode" in record && record.errorCode ? (
                <MiniBadge label={record.errorCode} tone="danger" />
              ) : null}
            </div>

            <FieldBlock label="Reason" value={record.reason} />
            {"jobId" in record && record.jobId ? (
              <JobContextCard record={record} />
            ) : null}

            {"requestHash" in record ? (
              <>
                {record.errorMessage ? (
                  <InlineError message={record.errorMessage} />
                ) : null}
                {record.interruptedReason ? (
                  <InlineError message={record.interruptedReason} tone="warn" />
                ) : null}
                <RelatedRecords records={record.relatedRecords} />
                <details className="rounded-md border bg-muted/15 px-3 py-2.5">
                  <summary className="cursor-pointer text-sm font-medium">
                    Technical details
                  </summary>
                  <div className="mt-4 space-y-4">
                    <FieldBlock
                      label="Idempotency Key"
                      value={record.idempotencyKey}
                      mono
                    />
                    <FieldBlock
                      label="Request Hash"
                      value={record.requestHash}
                      mono
                    />
                    <JsonBlock
                      title="Request Summary"
                      value={record.requestSummary}
                    />
                    <JsonBlock
                      title="Resolved Versions"
                      value={record.resolvedVersions}
                    />
                    <JsonBlock title="Metadata" value={record.metadata} />
                  </div>
                </details>
              </>
            ) : null}
          </div>
        ) : (
          <StatePanel label="Select a record" />
        )}
      </CardContent>
    </Card>
  );
}

function JobContextCard({
  record,
}: {
  record: AuditDetail | AuditListItem;
}) {
  const linkedJob = "linkedJob" in record ? record.linkedJob : null;
  const status = linkedJob?.status ?? ("jobStatus" in record ? record.jobStatus : null);
  const jobLabel = linkedJob
    ? `${linkedJob.jobType} ${linkedJob.status}`
    : status;

  return (
    <div className="rounded-md border bg-background p-3">
      <div className="text-xs font-semibold uppercase text-muted-foreground">
        Linked Job
      </div>
      <div className="mt-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          {record.jobId ? (
            <Link
              href="/jobs"
              className="truncate text-sm font-medium text-primary hover:underline"
            >
              {record.jobId}
            </Link>
          ) : null}
          <div className="mt-1 text-sm text-muted-foreground">
            {jobLabel ?? "Unavailable"}
          </div>
          {linkedJob ? (
            <div className="mt-1 text-sm text-muted-foreground">
              {linkedJob.submittedBy} · {formatDate(linkedJob.updatedAt)}
            </div>
          ) : null}
        </div>
        {status ? (
          <MiniBadge label={status} tone={jobTone(status)} />
        ) : null}
      </div>
      {"resultReference" in record && record.resultReference ? (
        <div className="mt-3">
          <FieldBlock
            label="Result Reference"
            value={record.resultReference}
            mono
          />
        </div>
      ) : null}
    </div>
  );
}

function RelatedRecords({ records }: { records: AuditListItem[] }) {
  if (!records.length) {
    return null;
  }

  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold uppercase text-muted-foreground">
        Related Correlation Records
      </div>
      <div className="divide-y rounded-md border">
        {records.map((record) => (
          <div
            key={record.auditId}
            className="grid gap-2 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_120px]"
          >
            <div className="min-w-0">
              <div className="truncate font-mono text-xs font-medium">
                {record.auditId}
              </div>
              <div className="mt-1 truncate text-sm text-muted-foreground">
                {record.toolName}
              </div>
            </div>
            <div className="flex items-center justify-start sm:justify-end">
              <AuditStatusBadge record={record} compact />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CompactSearchField({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex h-9 items-center gap-2 rounded-md border border-input bg-background px-3 shadow-sm focus-within:ring-2 focus-within:ring-ring">
      <Search className="h-4 w-4 text-muted-foreground" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search audit, request, correlation, job"
        aria-label="Search audit records"
        className="w-full border-0 bg-transparent p-0 text-sm outline-none"
      />
    </div>
  );
}

function CompactSelectField({
  value,
  options,
  placeholder,
  ariaLabel,
  onChange,
}: {
  value: string;
  options: string[];
  placeholder: string;
  ariaLabel: string;
  onChange: (value: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      aria-label={ariaLabel}
      className="h-9 min-w-0 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <option value="">{placeholder}</option>
      {options.map((option) => (
        <option key={option} value={option}>
          {humanizeToken(option)}
        </option>
      ))}
    </select>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
  optionLabels,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  optionLabels?: Record<string, string>;
}) {
  return (
    <label className="block">
      <LabelText>{label}</LabelText>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <option value="">Any</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {optionLabels?.[option] ?? humanizeToken(option)}
          </option>
        ))}
      </select>
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
          "mt-1 break-words text-sm font-medium",
          mono && "font-mono text-xs",
        )}
        title={value}
      >
        {value}
      </div>
    </div>
  );
}

function JsonBlock({
  title,
  value,
}: {
  title: string;
  value: Record<string, unknown>;
}) {
  return (
    <div>
      <LabelText>{title}</LabelText>
      <pre className="mt-1 max-h-52 overflow-auto rounded-md border bg-background p-3 text-xs leading-5">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function AuditStatusBadge({
  record,
  compact = false,
}: {
  record: Pick<AuditListItem, "status" | "interrupted">;
  compact?: boolean;
}) {
  const label = record.interrupted ? "INTERRUPTED" : humanizeToken(record.status);
  return (
    <Badge
      variant="outline"
      className={cn(
        "border-transparent font-semibold",
        compact ? "px-2 py-0.5 text-[11px]" : undefined,
        auditStatusClassName(record),
      )}
    >
      {label}
    </Badge>
  );
}

function MiniBadge({
  label,
  tone = "default",
}: {
  label: string;
  tone?: "default" | "warn" | "danger" | "success";
}) {
  const toneClassName = {
    default: "border-slate-200 bg-slate-50 text-slate-700",
    warn: "border-[#ffd60a] bg-[#fff7cc] text-[#7a5d00]",
    danger: "border-[#ff453a] bg-[#fff1f0] text-[#9f231a]",
    success: "border-[#32d74b] bg-[#eefbed] text-[#1f5f2a]",
  }[tone];

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-1 text-xs font-medium",
        toneClassName,
      )}
    >
      {humanizeToken(label)}
    </span>
  );
}

function LabelText({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-xs font-semibold uppercase text-muted-foreground">
      {children}
    </div>
  );
}

function StatePanel({ label }: { label: string }) {
  return (
    <div className="flex min-h-[220px] items-center justify-center rounded-md border bg-card text-sm text-muted-foreground">
      {label}
    </div>
  );
}

function EmptyPanel() {
  return (
    <div className="flex min-h-[220px] flex-col items-center justify-center rounded-md border bg-card px-4 py-6 text-center">
      <Workflow className="h-6 w-6 text-muted-foreground" />
      <div className="mt-3 text-sm font-semibold">No audit records found</div>
    </div>
  );
}

function ErrorPanel({ error }: { error: unknown }) {
  return (
    <div className="flex min-h-[220px] items-center justify-center gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-4 text-sm text-destructive">
      <AlertCircle className="h-4 w-4" />
      {formatError(error)}
    </div>
  );
}

function InlineError({
  message,
  tone = "danger",
}: {
  message: string;
  tone?: "danger" | "warn";
}) {
  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2 text-sm",
        tone === "danger"
          ? "border-destructive/40 bg-destructive/5 text-destructive"
          : "border-[#ffd60a] bg-[#fff7cc] text-[#7a5d00]",
      )}
    >
      {message}
    </div>
  );
}

function humanizeToken(value: string) {
  return value.replaceAll("_", " ");
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-AU", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDuration(value: number | null) {
  if (value === null) {
    return "In progress";
  }
  if (value < 1000) {
    return `${Math.round(value)} ms`;
  }
  return `${(value / 1000).toFixed(2)} s`;
}

function auditStatusClassName(
  record: Pick<AuditListItem, "status" | "interrupted">,
) {
  if (record.interrupted) {
    return "bg-[#ffd60a] text-[#1f2328]";
  }
  if (record.status === "SUCCEEDED") {
    return "bg-[#32d74b] text-[#1f2328]";
  }
  if (record.status === "FAILED") {
    return "bg-[#ff453a] text-[#1f2328]";
  }
  if (record.status === "DRY_RUN") {
    return "bg-secondary text-secondary-foreground";
  }
  return "bg-primary text-primary-foreground";
}

function auditSummary(metrics: AuditMetric[]) {
  const valueFor = (label: string) =>
    metrics.find((metric) => metric.label === label)?.value ?? 0;
  return {
    started: valueFor("Started"),
    interrupted: valueFor("Interrupted"),
    succeeded: valueFor("Succeeded"),
    failed: valueFor("Failed"),
    dryRun: valueFor("Dry Run"),
  };
}

function formatError(error: unknown) {
  if (error instanceof KavachApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "MCP audit request failed.";
}

function jobTone(status: string): "default" | "warn" | "danger" | "success" {
  if (status === "SUCCEEDED" || status === "APPROVED") {
    return "success";
  }
  if (status === "FAILED" || status === "REJECTED" || status === "BLOCKED") {
    return "danger";
  }
  if (status === "QUEUED" || status === "RUNNING" || status === "PROPOSED") {
    return "warn";
  }
  return "default";
}
