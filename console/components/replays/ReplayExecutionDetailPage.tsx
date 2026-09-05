"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getReplayExecution } from "@/lib/api/replays";

export function ReplayExecutionDetailPage({ executionId }: { executionId: string }) {
  const execution = useQuery({
    queryKey: ["replay-execution", executionId],
    queryFn: () => getReplayExecution(executionId),
  });

  if (execution.isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading execution…</div>;
  }
  if (execution.isError || !execution.data) {
    return <div className="p-6 text-sm text-destructive">Unable to load this execution.</div>;
  }

  const item = execution.data;
  return (
    <div className="studio-page flex flex-col gap-5">
      <Link
        href="/replays/new"
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Find another execution
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{item.workflow_name}</h1>
          <p className="mt-1 break-all font-mono text-sm text-muted-foreground">
            {item.execution_id}
          </p>
        </div>
        {item.replayable ? (
          <Button asChild>
            <Link href={`/replays/new?source_execution_id=${encodeURIComponent(item.execution_id)}`}>
              <Play className="h-4 w-4" />
              Create replay
            </Link>
          </Button>
        ) : null}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Historical execution</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Workflow ID" value={item.workflow_id} />
          <Field label="Workflow version" value={item.workflow_version} />
          <Field label="Execution status" value={item.execution_status} />
          <Field label="Created" value={item.created_at ? new Date(item.created_at).toLocaleString() : "Unknown"} />
          <div className="sm:col-span-2">
            <div className="text-xs text-muted-foreground">Replayability</div>
            <div className={item.replayable ? "mt-1 text-emerald-700" : "mt-1 text-destructive"}>
              {item.replayable ? "Replayable" : item.replayability_reason ?? "Not replayable"}
            </div>
          </div>
        </CardContent>
      </Card>
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
