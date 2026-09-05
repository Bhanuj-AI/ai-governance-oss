"use client";

import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, FlaskConical, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useSearchParams } from "next/navigation";
import { createExperiment, listExperiments } from "@/lib/api/experiments";
import { ExperimentStatusBadge } from "@/components/experiments/ExperimentStatusBadge";

const PAGE_SIZE_OPTIONS = [10, 25, 50];

export function ExperimentsPage() {
  const searchParams = useSearchParams();
  const query = useQuery({ queryKey: ["experiments"], queryFn: listExperiments });
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: createExperiment,
    onSuccess: (item) => { window.location.href = `/experiments/${item.experiment_id}`; },
    onError: (e) => setError(e instanceof Error ? e.message : "Unable to create experiment."),
  });
  const experiments = (query.data ?? [])
    .filter((experiment) => !statusFilter || experiment.status === statusFilter)
    .sort((left, right) => {
      const leftModified = new Date(left.updated_at ?? left.created_at).getTime();
      const rightModified = new Date(right.updated_at ?? right.created_at).getTime();
      return rightModified - leftModified;
    });
  const totalPages = Math.max(1, Math.ceil(experiments.length / pageSize));
  const currentPage = Math.min(page, totalPages - 1);
  const visibleExperiments = experiments.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
  const dialog = () => document.getElementById("create-experiment") as HTMLDialogElement | null;

  useEffect(() => {
    if (searchParams.get("onboarding") !== "create") return;
    const timer = window.setTimeout(() => dialog()?.showModal(), 0);
    return () => window.clearTimeout(timer);
  }, [searchParams]);

  function submit() {
    setError(null);
    if (!name.trim() || !description.trim()) { setError("Name and description are required."); return; }
    mutation.mutate({ name: name.trim(), description: description.trim() });
  }

  return <div className="studio-page flex flex-col gap-5">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><div className="flex items-center gap-2"><FlaskConical className="h-5 w-5 text-primary" /><h1 className="text-2xl font-semibold">Experiments</h1></div><p className="mt-1 text-sm text-muted-foreground">Compare governed AI configurations through controlled evaluation runs.</p></div>
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Filter experiments by status" className="h-9 rounded-md border bg-background px-3 text-sm" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(0); }}>
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="RUNNING">Running</option>
          <option value="COMPLETED">Completed</option>
          <option value="FAILED">Failed</option>
          <option value="ARCHIVED">Archived</option>
        </select>
        <Button onClick={() => dialog()?.showModal()}><Plus className="h-4 w-4" />Create Experiment</Button>
      </div>
    </div>
    <Card><CardContent className="p-0">
      <div className="border-b p-4"><h2 className="font-semibold">Experiments</h2><p className="mt-1 text-sm text-muted-foreground">Select an experiment to view candidates, runs, comparison, and leaderboard details.</p></div>
      {query.isLoading ? <div className="p-8 text-sm text-muted-foreground">Loading experiments…</div> : query.isError ? <div className="p-8 text-sm text-destructive">Unable to load experiments.</div> : experiments.length === 0 ? <div className="p-10 text-center text-sm text-muted-foreground">{statusFilter ? `No ${statusFilter.toLowerCase()} experiments found.` : <>No experiments have been created.<br />Create an experiment to compare governed AI configurations.</>}</div> : <>
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b text-muted-foreground"><th className="p-4">Name</th><th>Status</th><th>Owner</th><th>Last Modified</th><th className="pr-4 text-right">Action</th></tr></thead><tbody>{visibleExperiments.map((experiment) => <tr key={experiment.experiment_id} className="cursor-pointer border-b last:border-0 hover:bg-accent/40" onClick={() => { window.location.href = `/experiments/${experiment.experiment_id}`; }}><td className="p-4"><Link className="font-medium hover:underline" href={`/experiments/${experiment.experiment_id}`} onClick={(event) => event.stopPropagation()}>{experiment.name}</Link><div className="mt-1 max-w-md truncate text-xs text-muted-foreground">{experiment.description}</div></td><td><ExperimentStatusBadge status={experiment.status} /></td><td>{experiment.owner}</td><td>{new Date(experiment.updated_at ?? experiment.created_at).toLocaleString()}</td><td className="pr-4 text-right"><Link className="text-primary hover:underline" href={`/experiments/${experiment.experiment_id}`} onClick={(event) => event.stopPropagation()}>Open</Link></td></tr>)}</tbody></table></div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t p-4 text-sm"><span className="text-muted-foreground">Page {currentPage + 1} of {totalPages} · {experiments.length} experiments</span><div className="flex items-center gap-2"><label className="text-muted-foreground">Rows</label><select className="h-8 rounded-md border bg-background px-2" value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(0); }}>{PAGE_SIZE_OPTIONS.map((size) => <option key={size} value={size}>{size}</option>)}</select><Button variant="outline" size="sm" disabled={currentPage === 0} onClick={() => setPage((value) => value - 1)}><ChevronLeft className="h-4 w-4" />Previous</Button><Button variant="outline" size="sm" disabled={currentPage >= totalPages - 1} onClick={() => setPage((value) => value + 1)}>Next<ChevronRight className="h-4 w-4" /></Button></div></div>
      </>}
    </CardContent></Card>
    <dialog id="create-experiment" className="fixed left-1/2 top-1/2 m-0 max-h-[90vh] max-w-[92vw] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg border bg-card p-0 shadow-xl backdrop:bg-black/40"><div className="w-[min(92vw,480px)] p-5"><h2 className="text-lg font-semibold">Create Experiment</h2><p className="mt-1 text-sm text-muted-foreground">New experiments begin in DRAFT.</p><div className="mt-4 space-y-3"><Input placeholder="Name" value={name} onChange={(event) => setName(event.target.value)} /><textarea className="min-h-24 w-full rounded-md border bg-background p-3 text-sm" placeholder="Description or objective" value={description} onChange={(event) => setDescription(event.target.value)} />{error && <p className="text-sm text-destructive">{error}</p>}<div className="flex justify-end gap-2"><Button variant="outline" onClick={() => dialog()?.close()}>Cancel</Button><Button disabled={mutation.isPending} onClick={submit}>{mutation.isPending ? "Creating…" : "Create Experiment"}</Button></div></div></div></dialog>
  </div>;
}
