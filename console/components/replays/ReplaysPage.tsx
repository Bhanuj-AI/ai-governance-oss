"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  RefreshCw,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { Card, CardContent } from "@/components/ui/card";
import { useTenantContext } from "@/components/tenancy/TenantContextProvider";
import { getCurrentContext } from "@/lib/api/tenancy";
import { listReplays } from "@/lib/api/replays";
import type { ReplayStatus } from "@/types/replay";
import { ReplayStatusBadge } from "./ReplayStatusBadge";

const PAGE_SIZE_OPTIONS = [10, 25, 50];
const statuses: ReplayStatus[] = [
  "DRAFT",
  "READY",
  "QUEUED",
  "RUNNING",
  "EXECUTION_COMPLETED",
  "EVALUATING",
  "COMPARING",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
  "ARCHIVED",
];
const active = new Set<ReplayStatus>([
  "QUEUED",
  "RUNNING",
  "EVALUATING",
  "COMPARING",
]);

export function ReplaysPage() {
  const router = useRouter();
  const search = useSearchParams();
  const tenant = useTenantContext();
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const status = search.get("status") ?? "";
  const sourceExecutionId = search.get("source_execution_id") ?? "";
  const requestedBy = search.get("requested_by") ?? "";
  const permissions = useQuery({
    queryKey: ["current-context", tenant.organizationId, tenant.projectId],
    queryFn: getCurrentContext,
  });
  const replays = useQuery({
    queryKey: ["replays", status, sourceExecutionId, requestedBy],
    queryFn: () =>
      listReplays({
        status,
        source_execution_id: sourceExecutionId,
        requested_by: requestedBy,
        limit: 200,
      }),
    refetchInterval: (query) =>
      query.state.data?.some((item) => active.has(item.status)) ? 5000 : false,
  });
  const canCreate = permissions.data?.permissions.includes("replay.create") ?? false;
  const items = useMemo(() => replays.data ?? [], [replays.data]);
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(page, totalPages - 1);
  const visibleItems = items.slice(
    currentPage * pageSize,
    (currentPage + 1) * pageSize,
  );

  function updateFilter(name: string, value: string) {
    const params = new URLSearchParams(search.toString());
    if (value) {
      params.set(name, value);
    } else {
      params.delete(name);
    }
    setPage(0);
    router.replace(`/replays${params.size ? `?${params}` : ""}`);
  }

  return (
    <div className="mx-auto flex w-full max-w-[1320px] flex-col gap-5 px-6 py-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Replay Management</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Create and inspect governed reproductions of historical executions.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void replays.refetch()}
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          {canCreate ? (
            <Button asChild>
              <Link href="/replays/new">
                <Plus className="h-4 w-4" />
                Create Replay
              </Link>
            </Button>
          ) : null}
        </div>
      </div>
      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="grid gap-3 md:grid-cols-3">
            <select
              aria-label="Replay status"
              className="h-9 rounded-md border bg-background px-3 text-sm"
              value={status}
              onChange={(event) => updateFilter("status", event.target.value)}
            >
              <option value="">All statuses</option>
              {statuses.map((item) => (
                <option key={item} value={item}>
                  {item.replaceAll("_", " ")}
                </option>
              ))}
            </select>
            <input
              aria-label="Source execution ID"
              className="h-9 rounded-md border bg-background px-3 text-sm"
              placeholder="Source execution ID"
              value={sourceExecutionId}
              onChange={(event) =>
                updateFilter("source_execution_id", event.target.value)
              }
            />
            <input
              aria-label="Requested by"
              className="h-9 rounded-md border bg-background px-3 text-sm"
              placeholder="Requested by"
              value={requestedBy}
              onChange={(event) =>
                updateFilter("requested_by", event.target.value)
              }
            />
          </div>
          {replays.isLoading ? (
            <div className="py-10 text-sm text-muted-foreground">
              Loading replays…
            </div>
          ) : replays.isError ? (
            <div className="py-10 text-sm text-destructive">
              Unable to load replays. Check your access and selected tenant.
            </div>
          ) : items.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              {status || sourceExecutionId || requestedBy
                ? "No replays match the selected filters."
                : "No replays have been created for this project."}
              <div className="mt-3">
                {canCreate ? (
                  <Link className="text-primary hover:underline" href="/replays/new">
                    Create a replay from a historical workflow execution.
                  </Link>
                ) : null}
              </div>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1080px] text-left text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="p-3">Replay</th>
                      <th>Source</th>
                      <th>Status</th>
                      <th>Drift</th>
                      <th>Result</th>
                      <th>Created by</th>
                      <th>Created</th>
                      <th className="text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleItems.map((replay) => (
                      <tr
                        key={replay.replay_id}
                        className="border-b last:border-0 hover:bg-accent/35"
                      >
                        <td className="p-3">
                          <Link
                            className="font-medium hover:underline"
                            href={`/replays/${replay.replay_id}`}
                          >
                            {shortId(replay.replay_id)}
                          </Link>
                          <CopyButton
                            value={replay.replay_id}
                            variant="ghost"
                            size="sm"
                            className="ml-2 h-auto w-auto p-0 text-muted-foreground hover:text-foreground"
                            copyTitle="Copy replay ID"
                            iconClassName="h-3.5 w-3.5"
                          />
                        </td>
                        <td className="p-3">
                          <span className="font-mono text-xs">
                            {replay.source_execution_id}
                          </span>
                          <CopyButton
                            value={replay.source_execution_id}
                            variant="ghost"
                            size="sm"
                            className="ml-2 h-auto w-auto p-0 text-muted-foreground hover:text-foreground"
                            copyTitle="Copy source execution ID"
                            iconClassName="h-3.5 w-3.5"
                          />
                        </td>
                        <td>
                          <ReplayStatusBadge status={replay.status} />
                        </td>
                        <td>
                          {replay.status === "COMPLETED"
                            ? "Available in result"
                            : "—"}
                        </td>
                        <td>{replay.result_id ? "Evidence ready" : "Not created"}</td>
                        <td>{replay.requested_by}</td>
                        <td>{formatDate(replay.created_at)}</td>
                        <td className="pr-3 text-right">
                          <Link
                            className="text-primary hover:underline"
                            href={`/replays/${replay.replay_id}`}
                          >
                            Open
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4 text-sm">
                <span className="text-muted-foreground">
                  Page {currentPage + 1} of {totalPages} · {items.length} replays
                </span>
                <div className="flex items-center gap-2">
                  <label className="text-muted-foreground">Rows</label>
                  <select
                    className="h-8 rounded-md border bg-background px-2"
                    value={pageSize}
                    onChange={(event) => {
                      setPageSize(Number(event.target.value));
                      setPage(0);
                    }}
                  >
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={currentPage === 0}
                    onClick={() => setPage((value) => value - 1)}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={currentPage >= totalPages - 1}
                    onClick={() => setPage((value) => value + 1)}
                  >
                    Next
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function shortId(value: string) {
  return value.length > 16 ? `${value.slice(0, 10)}…${value.slice(-4)}` : value;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}
