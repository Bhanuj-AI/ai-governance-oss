"use client";

import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createModelVersion, createPromptAsset, createPromptVersion, listRuntimeModelProviders, registerModelAsset, type ModelAsset, type ModelRegisterInput, type PromptCreateInput } from "@/lib/api/registries";

export function ManagedAssetForm({ kind }: { kind: "prompts" | "models" }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedProvider, setSelectedProvider] = useState("");
  const runtimeProviders = useQuery({ queryKey: ["runtime-model-providers"], queryFn: listRuntimeModelProviders, enabled: kind === "models" && open });
  const create = useMutation<unknown, Error, PromptCreateInput | ModelRegisterInput>({
    mutationFn: (payload: PromptCreateInput | ModelRegisterInput) => kind === "prompts"
      ? createPromptAsset(payload as PromptCreateInput)
      : registerModelAsset(payload as ModelRegisterInput),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ["asset-registry", kind] }); setOpen(false); setError(null); setSelectedProvider(""); },
    onError: (reason) => setError(reason instanceof Error ? reason.message : "Unable to save this managed asset."),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      setError(null);
      if (kind === "prompts") {
        create.mutate({ name: String(form.get("name")).trim(), version: String(form.get("version")).trim(), template: String(form.get("template")), variables: String(form.get("variables")).split(",").map((value) => value.trim()).filter(Boolean) });
      } else {
        const selected = String(form.get("provider")).trim();
        const customName = String(form.get("custom_provider")).trim();
        if (selected === "custom" && !customName) throw new Error("Enter the custom runtime provider name.");
        const provider = selected === "custom" ? `custom:${customName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")}` : selected;
        create.mutate({ provider, model_name: String(form.get("model_name")).trim(), version: String(form.get("version")).trim(), context_window: Number(form.get("context_window")), parameters: JSON.parse(String(form.get("parameters") || "{}")) });
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Model parameters must be a JSON object."); }
  }

  if (!open) return <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />{kind === "prompts" ? "Create Prompt" : "Register Model"}</Button>;
  return <form onSubmit={submit} className="grid w-full max-w-3xl gap-3 rounded-md border bg-card p-4 sm:grid-cols-2">
    <div className="sm:col-span-2"><div className="font-medium">{kind === "prompts" ? "Create managed prompt" : "Register managed model"}</div><p className="mt-1 text-xs text-muted-foreground">This creates an immutable managed DRAFT version. Runtime-observed assets remain separate.</p></div>
    {kind === "models" ? <label className="grid gap-1 text-sm">Runtime provider<select name="provider" required value={selectedProvider} disabled={runtimeProviders.isLoading} onChange={(event) => setSelectedProvider(event.target.value)} className="h-9 rounded-md border bg-background px-3 text-sm disabled:opacity-70"><option value="">{runtimeProviders.isLoading ? "Loading providers…" : "Select a provider"}</option>{(runtimeProviders.data ?? []).filter((provider) => provider.allowed).map((provider) => <option key={provider.key} value={provider.key}>{provider.display_name}</option>)}</select></label> : null}
    <label className="grid gap-1 text-sm">{kind === "prompts" ? "Name" : "Model name"}<Input name={kind === "prompts" ? "name" : "model_name"} required /></label>
    {kind === "models" && selectedProvider === "custom" ? <label className="grid gap-1 text-sm sm:col-span-2">Custom runtime provider<Input name="custom_provider" required placeholder="enterprise-gateway" /></label> : null}
    <label className="grid gap-1 text-sm">Version<Input name="version" required placeholder="v1" /></label>
    {kind === "prompts" ? <><label className="grid gap-1 text-sm sm:col-span-2">Template<textarea name="template" required className="min-h-28 rounded-md border bg-background p-3" /></label><label className="grid gap-1 text-sm sm:col-span-2">Variables (comma-separated)<Input name="variables" placeholder="context, question" /></label></> : <><label className="grid gap-1 text-sm">Context window<Input name="context_window" type="number" min="1" required placeholder="128000" /></label><label className="grid gap-1 text-sm sm:col-span-2">Parameters (JSON)<textarea name="parameters" defaultValue="{}" className="min-h-20 rounded-md border bg-background p-3 font-mono text-xs" /></label></>}
    {runtimeProviders.isError ? <p className="text-sm text-destructive sm:col-span-2">Unable to load the runtime-provider policy.</p> : null}
    {error ? <p className="text-sm text-destructive sm:col-span-2">{error}</p> : null}
    <div className="flex gap-2 sm:col-span-2"><Button type="submit" disabled={create.isPending}>{create.isPending ? "Saving…" : kind === "prompts" ? "Create Prompt" : "Register Model"}</Button><Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={create.isPending}>Cancel</Button></div>
  </form>;
}

export function PromptVersionForm({ promptId }: { promptId: string }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({ mutationFn: (payload: { version: string; template?: string; variables?: string[] }) => createPromptVersion(promptId, payload), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["asset-registry", "prompts"] }); await client.invalidateQueries({ queryKey: ["asset-versions", "prompts"] }); setOpen(false); }, onError: (reason) => setError(reason instanceof Error ? reason.message : "Unable to create the prompt version.") });
  if (!open) return <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Create New Version</Button>;
  return <form onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); create.mutate({ version: String(form.get("version")).trim(), template: String(form.get("template")), variables: String(form.get("variables")).split(",").map((value) => value.trim()).filter(Boolean) }); }} className="grid gap-3 rounded-md border bg-card p-4">
    <label className="grid gap-1 text-sm">Version<Input name="version" required placeholder="v2" /></label><label className="grid gap-1 text-sm">Template<textarea name="template" required className="min-h-28 rounded-md border bg-background p-3" /></label><label className="grid gap-1 text-sm">Variables (comma-separated)<Input name="variables" placeholder="context, question" /></label>{error ? <p className="text-sm text-destructive">{error}</p> : null}<div className="flex gap-2"><Button type="submit" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create Version"}</Button><Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button></div>
  </form>;
}

export function ModelVersionForm({ model }: { model: ModelAsset }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({ mutationFn: (payload: { version: string; parameters?: Record<string, unknown>; context_window?: number }) => createModelVersion(model.model_id, payload), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["asset-registry", "models"] }); setOpen(false); setError(null); }, onError: (reason) => setError(reason instanceof Error ? reason.message : "Unable to create the model version.") });
  if (!open) return <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Create New Version</Button>;
  return <form onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); try { setError(null); create.mutate({ version: String(form.get("version")).trim(), context_window: Number(form.get("context_window")), parameters: JSON.parse(String(form.get("parameters") || "{}")) }); } catch (reason) { setError(reason instanceof Error ? reason.message : "Model parameters must be a JSON object."); } }} className="grid gap-3 rounded-md border bg-card p-4">
    <div><div className="font-medium">Create managed model version</div><p className="mt-1 text-xs text-muted-foreground">{model.provider} · {model.model_name}. This creates an immutable DRAFT version.</p></div><label className="grid gap-1 text-sm">Version<Input name="version" required placeholder="v2" /></label><label className="grid gap-1 text-sm">Context window<Input name="context_window" type="number" min="1" required defaultValue={model.context_window} /></label><label className="grid gap-1 text-sm">Parameters (JSON)<textarea name="parameters" defaultValue={JSON.stringify(model.parameters, null, 2)} className="min-h-20 rounded-md border bg-background p-3 font-mono text-xs" /></label>{error ? <p className="text-sm text-destructive">{error}</p> : null}<div className="flex gap-2"><Button type="submit" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create Version"}</Button><Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={create.isPending}>Cancel</Button></div>
  </form>;
}
