"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  Database,
  FileSearch,
  Search,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useMemo, useState } from "react";
import { DecisionStatusBadge } from "@/components/decisions/DecisionStatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getDecisions } from "@/lib/api/decisions";
import { AIGovernanceApiError } from "@/lib/api/client";
import type { GovernanceDecision } from "@/types/decision";

const DECISION_FETCH_LIMIT = 500;
const PAGE_SIZE_OPTIONS = [10, 25, 50];
const STATUS_FILTERS = [
  { value: "ALL", label: "All" },
  { value: "BLOCKED", label: "Blocked" },
  { value: "REVIEW", label: "Review" },
  { value: "APPROVED", label: "Approved" },
] as const;

type StatusFilter = (typeof STATUS_FILTERS)[number]["value"];

export function DecisionListPage() {
  const router = useRouter();
  const [decisionId, setDecisionId] = useState("");
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const query = useQuery({
    queryKey: ["decisions", DECISION_FETCH_LIMIT],
    queryFn: () => getDecisions(DECISION_FETCH_LIMIT),
  });

  const decisions = useMemo(
    () => sortedDecisions(query.data?.decisions ?? []),
    [query.data?.decisions],
  );
  const filteredDecisions = useMemo(
    () => decisions.filter((decision) => matchesStatusFilter(decision.status, statusFilter)),
    [decisions, statusFilter],
  );
  const totalPages = Math.max(1, Math.ceil(filteredDecisions.length / pageSize));
  const currentPage = Math.min(pageIndex, totalPages - 1);
  const pagedDecisions = filteredDecisions.slice(
    currentPage * pageSize,
    currentPage * pageSize + pageSize,
  );

  function handleDecisionLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextDecisionId = decisionId.trim();
    if (nextDecisionId) {
      router.push(`/decisions/${encodeURIComponent(nextDecisionId)}`);
    }
  }

  function handlePageSizeChange(value: string) {
    setPageSize(Number(value));
    setPageIndex(0);
  }

  function handleStatusFilterChange(nextFilter: StatusFilter) {
    setStatusFilter(nextFilter);
    setPageIndex(0);
  }

  return (
    <div className="h-[calc(100vh-3.5rem)] overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-5 px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <FileSearch className="h-5 w-5 text-primary" />
              <h1 className="text-2xl font-semibold tracking-normal">
                Governance Decisions
              </h1>
            </div>
            <p className="mt-1 max-w-[720px] text-sm text-muted-foreground">
              Read-only decisions persisted by the AI Governance Control Plane Control Plane.
            </p>
          </div>
          <details className="rounded-md border bg-card px-3 py-2 text-xs text-muted-foreground">
            <summary className="cursor-pointer font-medium">Developer help</summary>
            <div className="mt-2">
              Demo seed: <span className="font-mono">POST /api/v1/ontology/demo/seed</span>
            </div>
          </details>
        </div>

        <div className="rounded-lg border bg-card p-3 shadow-sm">
          <form className="flex flex-wrap items-center gap-3" onSubmit={handleDecisionLookup}>
            <div className="flex shrink-0 items-center gap-2 text-sm font-medium">
              <Search className="h-4 w-4 text-primary" />
              Open by ID
            </div>
            <div className="min-w-[240px] flex-1">
              <Input
                value={decisionId}
                onChange={(event) => setDecisionId(event.target.value)}
                placeholder="decision:Candidate:candidate-1:APPROVE:..."
                className="h-9 font-mono"
                aria-label="Decision ID"
              />
            </div>
            <Button type="submit" size="sm" disabled={!decisionId.trim()}>
              <Search className="h-4 w-4" />
              Open
            </Button>
          </form>
        </div>

        <Card>
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2">
                <Database className="h-4 w-4 text-primary" />
                Decision Index
              </CardTitle>
              {decisions.length ? (
                <div className="flex flex-wrap items-center justify-end gap-3 text-sm text-muted-foreground">
                  <span>
                    Page {currentPage + 1} of {totalPages}
                  </span>
                  <label className="flex items-center gap-2">
                    <span className="text-xs font-medium uppercase">
                      Rows
                    </span>
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
              ) : null}
            </div>
          </CardHeader>
          <CardContent>
            {decisions.length ? (
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap gap-2" aria-label="Decision status filter">
                  {STATUS_FILTERS.map((filter) => {
                    const active = filter.value === statusFilter;
                    const count = decisions.filter((decision) => matchesStatusFilter(decision.status, filter.value)).length;
                    return (
                      <Button
                        key={filter.value}
                        type="button"
                        variant={active ? "secondary" : "outline"}
                        size="sm"
                        className={active ? "border-primary/30 bg-primary/10 text-primary" : ""}
                        onClick={() => handleStatusFilterChange(filter.value)}
                      >
                        {filter.label}
                        <span className="text-muted-foreground">{count}</span>
                      </Button>
                    );
                  })}
                </div>
                <span className="text-sm text-muted-foreground">
                  {filteredDecisions.length} matching decision{filteredDecisions.length === 1 ? "" : "s"}
                </span>
              </div>
            ) : null}
            {query.isLoading ? (
              <StatePanel label="Loading decisions..." />
            ) : query.isError ? (
              <ErrorPanel error={query.error} />
            ) : filteredDecisions.length ? (
              <>
                <div className="divide-y rounded-md border">
                  <div className="hidden gap-3 bg-muted/30 px-4 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground lg:grid lg:grid-cols-[1fr_180px_160px_120px_34px]">
                    <span>Decision</span>
                    <span>Target</span>
                    <span>Type</span>
                    <span>Confidence</span>
                    <span className="sr-only">Open</span>
                  </div>
                  {pagedDecisions.map((decision) => (
                    <DecisionRow
                      key={decision.decisionId}
                      decision={decision}
                    />
                  ))}
                </div>
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm text-muted-foreground">
                    Showing {currentPage * pageSize + 1}-
                    {Math.min((currentPage + 1) * pageSize, filteredDecisions.length)}{" "}
                    of {filteredDecisions.length} matching decisions
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
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
                      size="sm"
                      disabled={currentPage >= totalPages - 1}
                      onClick={() =>
                        setPageIndex((value) =>
                          Math.min(totalPages - 1, value + 1),
                        )
                      }
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </>
            ) : (
              <EmptyPanel filtered={statusFilter !== "ALL"} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function sortedDecisions(decisions: GovernanceDecision[]) {
  return [...decisions].sort((left, right) => {
    const createdDelta =
      new Date(right.provenance.createdAt).getTime() -
      new Date(left.provenance.createdAt).getTime();
    if (createdDelta !== 0) {
      return createdDelta;
    }
    return right.decisionId.localeCompare(left.decisionId);
  });
}

function DecisionRow({ decision }: { decision: GovernanceDecision }) {
  return (
    <Link
      href={`/decisions/${encodeURIComponent(decision.decisionId)}`}
      className="grid gap-3 px-4 py-3 transition-colors hover:bg-accent/55 lg:grid-cols-[1fr_180px_160px_120px_34px]"
    >
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="truncate font-mono text-sm font-semibold">
            {decision.decisionId}
          </span>
          <DecisionStatusBadge value={decision.status} />
        </div>
        <div className="mt-1 truncate text-sm text-muted-foreground">
          {decision.reason}
        </div>
      </div>
      <ListField
        label="Target"
        value={`${decision.target.targetType}/${decision.target.targetId}`}
      />
      <ListField label="Type" value={decision.decisionType} />
      <ListField label="Confidence" value={decision.confidence} />
      <div className="flex items-center justify-end">
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
      </div>
    </Link>
  );
}

function ListField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-medium uppercase text-muted-foreground lg:hidden">
        {label}
      </div>
      <div className="mt-1 truncate text-sm font-medium">{value}</div>
    </div>
  );
}

function EmptyPanel({ filtered = false }: { filtered?: boolean }) {
  return (
    <div className="flex min-h-[220px] flex-col items-center justify-center rounded-md border bg-background px-4 py-6 text-center">
      <ShieldCheck className="h-6 w-6 text-muted-foreground" />
      <div className="mt-3 text-sm font-semibold">{filtered ? "No matching decisions" : "No decisions found"}</div>
      <div className="mt-1 max-w-[560px] text-sm leading-6 text-muted-foreground">
        {filtered ? "Try a different status filter to see more persisted decisions." : "Run the demo seed endpoint to create the ontology sample and a persisted governance decision, then refresh this page."}
      </div>
      {!filtered ? <div className="mt-3 rounded-md border bg-card px-3 py-2 font-mono text-xs">curl -X POST http://localhost:8000/api/v1/ontology/demo/seed</div> : null}
    </div>
  );
}

function matchesStatusFilter(status: string, filter: StatusFilter) {
  const normalized = status.toLowerCase();
  if (filter === "ALL") return true;
  if (filter === "BLOCKED") return ["blocked", "rejected", "reject", "denied", "deny"].includes(normalized);
  if (filter === "REVIEW") return ["pending", "proposed", "review", "investigate", "recommend"].includes(normalized);
  return ["approved", "approve", "active", "completed"].includes(normalized);
}

function ErrorPanel({ error }: { error: Error }) {
  const message =
    error instanceof AIGovernanceApiError
      ? `${error.code}: ${error.message}`
      : error.message;

  return (
    <div className="flex min-h-[180px] items-center justify-center gap-2 rounded-md border border-destructive/30 bg-background px-4 py-6 text-sm text-destructive">
      <AlertCircle className="h-4 w-4" />
      {message}
    </div>
  );
}

function StatePanel({ label }: { label: string }) {
  return (
    <div className="flex min-h-[180px] items-center justify-center rounded-md border bg-background text-sm text-muted-foreground">
      {label}
    </div>
  );
}
