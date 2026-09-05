"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { listAgentExecutions } from "@/lib/api/agent-runtime";

const PAGE_SIZE = 25;

type PickerContentProps = {
  onClose: () => void;
  onSelect: (executionId: string) => void;
};

function PickerContent({ onClose, onSelect }: PickerContentProps) {
  const [cursorStack, setCursorStack] = useState<string[]>([]);
  const cursor = cursorStack.at(-1);
  const executions = useQuery({
    queryKey: ["agent-executions", "policy-picker", cursor],
    queryFn: () => listAgentExecutions({ status: "SUCCEEDED", cursor, limit: PAGE_SIZE }),
  });
  const items = executions.data?.items ?? [];

  return <div className="flex max-h-[min(44rem,calc(100vh-4rem))] flex-col bg-background">
    <div className="flex items-start justify-between gap-4 border-b px-6 py-5">
      <div><p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">Observed evidence</p><h2 className="mt-1 text-xl font-semibold tracking-tight">Choose an execution</h2><p className="mt-1 text-sm text-muted-foreground">Select a completed execution, then choose one of its schema-described tool results in the policy form.</p></div>
      <Button type="button" variant="ghost" size="icon" onClick={onClose} aria-label="Close execution picker"><X className="h-4 w-4" /></Button>
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto p-6">
      {executions.isLoading ? <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">Loading completed executions…</div> : null}
      {executions.isError ? <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">Completed executions could not be loaded. Try again.</div> : null}
      {executions.isSuccess && items.length === 0 ? <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">No completed executions are available in this tenant.</div> : null}
      {items.length > 0 ? <div className="overflow-hidden rounded-md border"><table className="w-full text-sm"><thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-4 py-3">Execution</th><th className="px-4 py-3">Agent</th><th className="hidden px-4 py-3 md:table-cell">Runtime</th><th className="hidden px-4 py-3 lg:table-cell">Completed</th><th className="px-4 py-3"><span className="sr-only">Select</span></th></tr></thead><tbody className="divide-y">{items.map((execution) => <tr key={execution.executionId} className="hover:bg-muted/30"><td className="px-4 py-3 font-mono text-xs">{execution.externalExecutionId}</td><td className="px-4 py-3"><div className="font-medium">{execution.agentName || execution.agentId}</div><div className="mt-0.5 text-xs text-muted-foreground">{execution.eventCount} events</div></td><td className="hidden px-4 py-3 text-muted-foreground md:table-cell">{execution.runtimeProvider}</td><td className="hidden px-4 py-3 text-muted-foreground lg:table-cell">{formatDate(execution.completedAt)}</td><td className="px-4 py-3 text-right"><Button type="button" size="sm" variant="outline" onClick={() => onSelect(execution.executionId)}>Use <ChevronRight className="h-3.5 w-3.5" /></Button></td></tr>)}</tbody></table></div> : null}
    </div>
    <div className="flex items-center justify-between border-t bg-muted/10 px-6 py-4"><p className="text-sm text-muted-foreground">{cursorStack.length === 0 ? "Page 1" : `Page ${cursorStack.length + 1}`} · {PAGE_SIZE} per page</p><div className="flex gap-2"><Button type="button" variant="outline" size="sm" disabled={cursorStack.length === 0 || executions.isLoading} onClick={() => setCursorStack((stack) => stack.slice(0, -1))}><ChevronLeft className="h-3.5 w-3.5" />Previous</Button><Button type="button" variant="outline" size="sm" disabled={!executions.data?.nextCursor || executions.isLoading} onClick={() => setCursorStack((stack) => [...stack, executions.data!.nextCursor!])}>Next<ChevronRight className="h-3.5 w-3.5" /></Button></div></div>
  </div>;
}

function formatDate(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

export function ExecutionPickerModal() {
  const router = useRouter();
  const close = () => router.back();
  const select = (executionId: string) => router.replace(`/agents-runtime?view=policies&policyExecution=${encodeURIComponent(executionId)}`);
  return <Dialog.Root open onOpenChange={(open) => { if (!open) close(); }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(72rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-lg border bg-background shadow-xl"><Dialog.Title className="sr-only">Choose an observed execution</Dialog.Title><Dialog.Description className="sr-only">Paginated completed executions available to use as the source for an intervention policy.</Dialog.Description><PickerContent onClose={close} onSelect={select} /></Dialog.Content></Dialog.Portal></Dialog.Root>;
}

export function ExecutionPickerPage() {
  const router = useRouter();
  const close = () => router.replace("/agents-runtime?view=policies");
  const select = (executionId: string) => router.replace(`/agents-runtime?view=policies&policyExecution=${encodeURIComponent(executionId)}`);
  return <main className="mx-auto max-w-6xl p-6"><div className="overflow-hidden rounded-lg border shadow-sm"><PickerContent onClose={close} onSelect={select} /></div></main>;
}
