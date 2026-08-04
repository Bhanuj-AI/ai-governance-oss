"use client";

import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { KavachApiError } from "@/lib/api/client";
import { uploadDatasetAsset } from "@/lib/api/registries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function DatasetUploadForm({ openInitially = false }: { openInitially?: boolean }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(openInitially);
  const [error, setError] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: uploadDatasetAsset,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["asset-registry", "datasets"] });
      setOpen(false);
      setError(null);
    },
    onError: (reason) =>
      setError(reason instanceof KavachApiError ? reason.message : "Dataset upload failed."),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (!(form.get("file") instanceof File) || !(form.get("file") as File).name) {
      setError("Choose a CSV or JSONL file to register.");
      return;
    }
    setError(null);
    upload.mutate(form);
  }

  if (!open) return <Button onClick={() => setOpen(true)}><Upload className="h-4 w-4" />Register Dataset</Button>;

  return <form onSubmit={submit} className="grid gap-3 rounded-md border bg-card p-4 sm:grid-cols-2">
    <div className="sm:col-span-2"><div className="text-sm font-medium">Register Dataset Version</div><p className="mt-1 text-xs text-muted-foreground">Upload UTF-8 CSV or JSONL. Kavach stores immutable bytes in the configured S3-compatible store and registers a draft version.</p></div>
    <label className="grid gap-1 text-sm">Name<Input name="name" required placeholder="Support evaluation set" /></label>
    <label className="grid gap-1 text-sm">Version<Input name="version" required placeholder="v1.0" /></label>
    <label className="grid gap-1 text-sm sm:col-span-2">Description<Input name="description" required placeholder="What this evaluation dataset is for" /></label>
    <label className="grid gap-1 text-sm">Schema Version<Input name="schema_version" defaultValue="1.0" required /></label>
    <label className="grid gap-1 text-sm">File<Input name="file" type="file" accept=".csv,.jsonl,.ndjson,text/csv,application/x-ndjson" required /></label>
    {error ? <p className="sm:col-span-2 text-sm text-destructive">{error}</p> : null}
    <div className="flex gap-2 sm:col-span-2"><Button type="submit" disabled={upload.isPending}>{upload.isPending ? "Registering…" : "Upload and register"}</Button><Button type="button" variant="outline" disabled={upload.isPending} onClick={() => { setOpen(false); setError(null); }}>Cancel</Button></div>
  </form>;
}
