"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ShieldCheck, Workflow } from "lucide-react";
import { getInvocationAuditPage } from "@/lib/api/invocation-audit";

export function McpInvocationAuditPage() {
  const query = useQuery({
    queryKey: ["mcp-invocation-audit"],
    queryFn: () => getInvocationAuditPage({ limit: 100 }),
  });

  return (
    <div className="studio-page flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-primary" />
            <h1 className="text-2xl font-semibold">All MCP Invocations</h1>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Durable, redacted evidence of every MCP tool call, including read-only access.
          </p>
        </div>
      </div>
      <nav
        aria-label="MCP audit views"
        className="flex w-fit rounded-md border bg-muted/30 p-1 text-sm"
      >
        <Link
          href="/audit"
          className="flex items-center gap-2 rounded px-3 py-2 font-medium text-muted-foreground hover:bg-background hover:text-foreground"
        >
          <ShieldCheck className="h-4 w-4" />
          MCP Write Mutations
        </Link>
        <Link
          href="/audit/invocations"
          aria-current="page"
          className="flex items-center gap-2 rounded bg-primary px-3 py-2 font-semibold text-primary-foreground shadow-sm"
        >
          <Workflow className="h-4 w-4" />
          All MCP Invocations
        </Link>
      </nav>
      {query.isLoading ? <p>Loading MCP invocations…</p> : null}
      {query.isError ? <p role="alert">Unable to load MCP invocations.</p> : null}
      {query.data ? (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-left text-xs uppercase text-muted-foreground">
              <tr><th className="p-3">Tool</th><th className="p-3">Actor / client</th><th className="p-3">Outcome</th><th className="p-3">Started</th><th className="p-3">Duration</th></tr>
            </thead>
            <tbody>
              {query.data.records.map((record) => (
                <tr key={record.invocationId} className="border-b last:border-0">
                  <td className="p-3 font-mono">{record.toolName}</td>
                  <td className="p-3">{record.actorId ?? "unknown"}{record.clientId ? ` · ${record.clientId}` : ""}</td>
                  <td className="p-3">{record.status}{record.errorCategory ? ` · ${record.errorCategory}` : ""}</td>
                  <td className="p-3">{new Date(record.startedAt).toLocaleString()}</td>
                  <td className="p-3">{record.durationMs ? `${Math.round(record.durationMs)} ms` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.data.records.length === 0 ? <p className="p-4 text-sm text-muted-foreground">No MCP invocations in this tenant scope.</p> : null}
        </div>
      ) : null}
    </div>
  );
}
