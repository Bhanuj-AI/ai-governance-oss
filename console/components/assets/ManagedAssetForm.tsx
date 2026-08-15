"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createModelVersion, createPromptAsset, createPromptVersion, listRuntimeModelProviders, registerModelAsset, resolveModelRuntimeCapabilities, type ModelAsset, type ModelRegisterInput, type ModelRuntimeCapabilities, type ModelVersionCreateInput, type PromptCreateInput } from "@/lib/api/registries";
import { discoverRuntimeConnectionModels, listRuntimeConnections } from "@/lib/api/runtime-connections";

type RuntimeDefaults = Record<string, number>;

function supportedRuntimeDefaults(
  capabilities: ModelRuntimeCapabilities | undefined,
  parameters: Record<string, unknown> = {},
): RuntimeDefaults {
  if (!capabilities) return {};
  return Object.fromEntries(
    capabilities.parameters
      .filter((parameter) => parameter.supported)
      .flatMap((parameter) => {
        const value = parameters[parameter.name] ?? (
          parameter.name === "max_output_tokens" ? parameters.max_tokens : undefined
        );
        return typeof value === "number" ? [[parameter.name, value]] : [];
      }),
  );
}

function RuntimeDefaultsForm({
  capabilities,
  values,
  onChange,
  requiresMaxOutputTokens = false,
}: {
  capabilities: ModelRuntimeCapabilities;
  values: RuntimeDefaults;
  onChange: (values: RuntimeDefaults) => void;
  requiresMaxOutputTokens?: boolean;
}) {
  const parameters = capabilities.parameters.filter((parameter) => parameter.supported);
  if (parameters.length === 0) {
    return <p className="rounded-md border p-3 text-sm text-muted-foreground">This provider has no verified editable runtime controls yet. Provider defaults will be used.</p>;
  }
  return <section className="grid gap-3 rounded-md border p-3 sm:col-span-2">
    <div><div className="font-medium text-sm">Runtime defaults</div><p className="mt-1 text-xs text-muted-foreground">{requiresMaxOutputTokens ? "Anthropic requires a maximum output-token value. Other blank controls use the provider default." : "Only controls supported by this model are shown. Leave a value blank to use the provider default."}</p></div>
    <div className="grid gap-3 sm:grid-cols-3">{parameters.map((parameter) => <label key={parameter.name} className="grid gap-1 text-sm">{parameter.name.replaceAll("_", " ")}{requiresMaxOutputTokens && parameter.name === "max_output_tokens" ? " *" : ""}<Input name={`runtime-default-${parameter.name}`} type="number" step={parameter.value_type === "integer" ? "1" : "any"} min={parameter.minimum ?? undefined} max={parameter.maximum ?? undefined} required={requiresMaxOutputTokens && parameter.name === "max_output_tokens"} placeholder={parameter.default == null ? "Provider default" : String(parameter.default)} value={values[parameter.name] ?? ""} onChange={(event) => { const next = { ...values }; if (event.target.value === "") delete next[parameter.name]; else next[parameter.name] = Number(event.target.value); onChange(next); }} /></label>)}</div>
  </section>;
}

export function ManagedAssetForm({ kind }: { kind: "prompts" | "models" }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedProvider, setSelectedProvider] = useState("");
  const [modelName, setModelName] = useState("");
  const [providerModelId, setProviderModelId] = useState("");
  const [catalogConnectionId, setCatalogConnectionId] = useState("");
  const [runtimeDefaults, setRuntimeDefaults] = useState<RuntimeDefaults>({});
  const runtimeProviders = useQuery({ queryKey: ["runtime-model-providers"], queryFn: listRuntimeModelProviders, enabled: kind === "models" && open });
  const runtimeConnections = useQuery({ queryKey: ["runtime-connections"], queryFn: listRuntimeConnections, enabled: kind === "models" && open });
  const compatibleRuntimeConnections = (runtimeConnections.data ?? []).filter((connection) => connection.enabled && connection.provider === selectedProvider);
  const discoveredModels = useQuery({ queryKey: ["runtime-connection-models", catalogConnectionId], queryFn: () => discoverRuntimeConnectionModels(catalogConnectionId), enabled: kind === "models" && open && Boolean(catalogConnectionId) });
  const capabilities = useQuery({ queryKey: ["runtime-model-capabilities", selectedProvider, providerModelId], queryFn: () => resolveModelRuntimeCapabilities({ provider: selectedProvider, model_name: modelName, provider_model_id: providerModelId }), enabled: kind === "models" && open && Boolean(selectedProvider && modelName.trim() && providerModelId.trim()) });
  useEffect(() => { setRuntimeDefaults({}); }, [selectedProvider, providerModelId]);
  const create = useMutation<unknown, Error, PromptCreateInput | ModelRegisterInput>({
    mutationFn: (payload: PromptCreateInput | ModelRegisterInput) => kind === "prompts"
      ? createPromptAsset(payload as PromptCreateInput)
      : registerModelAsset(payload as ModelRegisterInput),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ["asset-registry", kind] }); setOpen(false); setError(null); setSelectedProvider(""); setProviderModelId(""); setCatalogConnectionId(""); },
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
        create.mutate({ provider, model_name: String(form.get("model_name")).trim(), provider_model_id: providerModelId.trim(), version: String(form.get("version")).trim(), context_window: Number(form.get("context_window")), parameters: runtimeDefaults });
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to validate the managed model."); }
  }

  if (!open) return <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />{kind === "prompts" ? "Create Prompt" : "Register Model"}</Button>;
  return <form onSubmit={submit} className="grid w-full max-w-3xl gap-3 rounded-md border bg-card p-4 sm:grid-cols-2">
    <div className="sm:col-span-2"><div className="font-medium">{kind === "prompts" ? "Create managed prompt" : "Register Managed Model"}</div><p className="mt-1 text-xs text-muted-foreground">This creates an immutable managed DRAFT version. Runtime-observed assets remain separate.</p></div>
    {kind === "models" ? <label className="grid gap-1 text-sm">Runtime Provider<select name="provider" required value={selectedProvider} disabled={runtimeProviders.isLoading} onChange={(event) => setSelectedProvider(event.target.value)} className="h-9 rounded-md border bg-background px-3 text-sm disabled:opacity-70"><option value="">{runtimeProviders.isLoading ? "Loading providers…" : "Select a provider"}</option>{(runtimeProviders.data ?? []).filter((provider) => provider.allowed).map((provider) => <option key={provider.key} value={provider.key}>{provider.display_name}</option>)}</select></label> : null}
    <label className="grid gap-1 text-sm">{kind === "prompts" ? "Name" : "Governed Model Name"}<Input name={kind === "prompts" ? "name" : "model_name"} required value={kind === "models" ? modelName : undefined} onChange={kind === "models" ? (event) => setModelName(event.target.value) : undefined} placeholder={kind === "models" ? "Claims assistant" : undefined} /></label>
    {kind === "models" && selectedProvider === "custom" ? <label className="grid gap-1 text-sm sm:col-span-2">Custom Runtime Provider<Input name="custom_provider" required placeholder="enterprise-gateway" /></label> : null}
    {kind === "models" ? <label className="grid gap-1 text-sm">Runtime connection<select value={catalogConnectionId} onChange={(event) => { setCatalogConnectionId(event.target.value); setProviderModelId(""); }} className="h-9 rounded-md border bg-background px-3 text-sm"><option value="">Select an active {selectedProvider || "provider"} connection</option>{compatibleRuntimeConnections.map((connection) => <option key={connection.runtime_connection_id} value={connection.runtime_connection_id}>{connection.display_name}</option>)}</select><span className="text-xs text-muted-foreground">Required to discover provider models. Create and validate it in <Link className="text-primary underline underline-offset-2" href="/settings?section=runtime-connections">Settings → Runtime Connections</Link>; it holds the private <code>env://</code> secret reference.</span>{selectedProvider && !runtimeConnections.isLoading && compatibleRuntimeConnections.length === 0 ? <span className="text-xs text-amber-700">No active {selectedProvider} Runtime Connection is available. Create and validate one in Settings before selecting a provider model.</span> : null}</label> : null}
    {kind === "models" ? <label className="grid gap-1 text-sm">Provider Model ID<select name="provider_model_id" required value={providerModelId} disabled={!catalogConnectionId || discoveredModels.isLoading} onChange={(event) => setProviderModelId(event.target.value)} className="h-9 rounded-md border bg-background px-3 text-sm disabled:opacity-70"><option value="">{discoveredModels.isLoading ? "Discovering models…" : "Select a provider model"}</option>{(discoveredModels.data ?? []).map((model) => <option key={model.provider_model_id} value={model.provider_model_id}>{model.provider_model_id}</option>)}</select>{discoveredModels.isError ? <span className="text-xs text-destructive">Unable to discover models for this connection. Confirm provider access and retry.</span> : <span className="text-xs text-muted-foreground">Exact identifier sent to the provider.</span>}</label> : null}
    <label className="grid gap-1 text-sm">Version<Input name="version" required placeholder="v1" /></label>
    {kind === "prompts" ? <><label className="grid gap-1 text-sm sm:col-span-2">Template<textarea name="template" required className="min-h-28 rounded-md border bg-background p-3" /></label><label className="grid gap-1 text-sm sm:col-span-2">Variables (comma-separated)<Input name="variables" placeholder="context, question" /></label></> : <><label className="grid gap-1 text-sm">Context window<Input name="context_window" type="number" min="1" required placeholder="128000" /></label>{capabilities.data ? <RuntimeDefaultsForm capabilities={capabilities.data} values={runtimeDefaults} onChange={setRuntimeDefaults} requiresMaxOutputTokens={selectedProvider === "anthropic"} /> : <p className="text-sm text-muted-foreground sm:col-span-2">Enter a provider, governed model name, and provider model ID to load available runtime controls.</p>}</>}
    {runtimeProviders.isError ? <p className="text-sm text-destructive sm:col-span-2">Unable to load the runtime-provider policy.</p> : null}
    {error ? <p className="text-sm text-destructive sm:col-span-2">{error}</p> : null}
    <div className="flex gap-2 sm:col-span-2"><Button type="submit" disabled={create.isPending || (kind === "models" && selectedProvider === "openai" && (!catalogConnectionId || !providerModelId))}>{create.isPending ? "Saving…" : kind === "prompts" ? "Create Prompt" : "Register Model"}</Button><Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={create.isPending}>Cancel</Button></div>
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
  const [runtimeDefaults, setRuntimeDefaults] = useState<RuntimeDefaults>({});
  const [providerModelId, setProviderModelId] = useState(model.provider_model_id ?? model.model_name);
  const [catalogConnectionId, setCatalogConnectionId] = useState("");
  const requiresModelDiscovery = model.provider.toLowerCase() === "openai";
  const legacyCapabilities = model.runtime_capabilities.profile_id === "legacy-runtime-contract";
  const capabilityRefreshRequired = legacyCapabilities || providerModelId !== (model.provider_model_id ?? model.model_name);
  const resolvedCapabilities = useQuery({ queryKey: ["runtime-model-capabilities", model.provider, providerModelId], queryFn: () => resolveModelRuntimeCapabilities({ provider: model.provider, model_name: model.model_name, provider_model_id: providerModelId }), enabled: open && capabilityRefreshRequired && Boolean(providerModelId.trim()) });
  const runtimeConnections = useQuery({ queryKey: ["runtime-connections"], queryFn: listRuntimeConnections, enabled: open });
  const compatibleRuntimeConnections = (runtimeConnections.data ?? []).filter((connection) => connection.enabled && connection.provider.toLowerCase() === model.provider.toLowerCase());
  const discoveredModels = useQuery({ queryKey: ["runtime-connection-models", catalogConnectionId], queryFn: () => discoverRuntimeConnectionModels(catalogConnectionId), enabled: open && Boolean(catalogConnectionId) });
  const versionCapabilities = capabilityRefreshRequired ? resolvedCapabilities.data : model.runtime_capabilities;
  useEffect(() => {
    if (open && resolvedCapabilities.data) setRuntimeDefaults(supportedRuntimeDefaults(resolvedCapabilities.data, model.parameters));
  }, [open, resolvedCapabilities.data, model.parameters]);
  const create = useMutation({ mutationFn: (payload: ModelVersionCreateInput) => createModelVersion(model.model_id, payload), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["asset-registry", "models"] }); setOpen(false); setError(null); }, onError: (reason) => setError(reason instanceof Error ? reason.message : "Unable to create the model version.") });
  if (!open) return <Button onClick={() => { setProviderModelId(model.provider_model_id ?? model.model_name); setCatalogConnectionId(""); setRuntimeDefaults(supportedRuntimeDefaults(model.runtime_capabilities, model.parameters)); setOpen(true); }}><Plus className="h-4 w-4" />Create New Version</Button>;
  return <form onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); setError(null); create.mutate({ version: String(form.get("version")).trim(), provider_model_id: providerModelId.trim(), context_window: Number(form.get("context_window")), parameters: runtimeDefaults }); }} className="grid gap-3 rounded-md border bg-card p-4">
    <div><div className="font-medium">Create managed model version</div><p className="mt-1 text-xs text-muted-foreground">{model.provider} · {model.model_name}. This creates an immutable DRAFT version.</p></div><label className="grid gap-1 text-sm">Version<Input name="version" required placeholder="v2" /></label><label className="grid gap-1 text-sm">Runtime connection<select value={catalogConnectionId} onChange={(event) => { setCatalogConnectionId(event.target.value); setProviderModelId(""); setRuntimeDefaults({}); }} className="h-9 rounded-md border bg-background px-3 text-sm"><option value="">Select an active {model.provider} connection</option>{compatibleRuntimeConnections.map((connection) => <option key={connection.runtime_connection_id} value={connection.runtime_connection_id}>{connection.display_name}</option>)}</select><span className="text-xs text-muted-foreground">Required to discover provider models. Configure it in <Link className="text-primary underline underline-offset-2" href="/settings?section=runtime-connections">Settings → Runtime Connections</Link>; it holds the private secret reference.</span>{!runtimeConnections.isLoading && compatibleRuntimeConnections.length === 0 ? <span className="text-xs text-amber-700">No active {model.provider} Runtime Connection is available. Create and validate one in Settings before selecting a provider model.</span> : null}</label><label className="grid gap-1 text-sm">Provider model ID<select name="provider_model_id" required value={providerModelId} disabled={!catalogConnectionId || discoveredModels.isLoading} onChange={(event) => { setProviderModelId(event.target.value); setRuntimeDefaults({}); }} className="h-9 rounded-md border bg-background px-3 text-sm disabled:opacity-70"><option value="">{discoveredModels.isLoading ? "Discovering models…" : "Select a provider model"}</option>{(discoveredModels.data ?? []).map((item) => <option key={item.provider_model_id} value={item.provider_model_id}>{item.provider_model_id}</option>)}</select>{discoveredModels.isError ? <span className="text-xs text-destructive">Unable to discover models for this connection.</span> : <span className="text-xs text-muted-foreground">Exact identifier sent to the provider.</span>}</label><label className="grid gap-1 text-sm">Context window<Input name="context_window" type="number" min="1" required defaultValue={model.context_window} /></label>{versionCapabilities ? <RuntimeDefaultsForm capabilities={versionCapabilities} values={runtimeDefaults} onChange={setRuntimeDefaults} requiresMaxOutputTokens={model.provider.toLowerCase() === "anthropic"} /> : <p className="rounded-md border p-3 text-sm text-muted-foreground">Loading runtime controls for this provider model ID…</p>}{error ? <p className="text-sm text-destructive">{error}</p> : null}<div className="flex gap-2"><Button type="submit" disabled={create.isPending || !providerModelId || (requiresModelDiscovery && !catalogConnectionId) || (capabilityRefreshRequired && resolvedCapabilities.isLoading)}>{create.isPending ? "Creating…" : "Create Version"}</Button><Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={create.isPending}>Cancel</Button></div>
  </form>;
}
