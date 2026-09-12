"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ChevronRight, Database, MessageSquareText, MoreHorizontal, Plus, Search, ShieldCheck, Sparkles } from "lucide-react";
import { AssetProvenanceBadge, StatusBadge, isAssetKind, selectLogicalAssets, type AssetKind } from "@/components/assets/AssetsPage";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { createProviderInstallation, listDatasetAssets, listModelAssets, listPromptAssets, listProviderAssets, listProviderInstallations, updateProviderInstallation, validateProviderInstallation, type ProviderAsset, type ProviderConfigurationField, type ProviderConfigurationSchema } from "@/lib/api/registries";
import { DatasetUploadForm } from "@/components/assets/DatasetUploadForm";
import { ManagedAssetForm } from "@/components/assets/ManagedAssetForm";

const TITLES: Record<AssetKind, { title: string; description: string; icon: typeof MessageSquareText }> = {
  prompts: { title: "Prompt Catalog", description: "Managed and observed prompt identities and immutable configurations.", icon: MessageSquareText },
  models: { title: "Model Catalog", description: "Registered and observed model/runtime configurations.", icon: Sparkles },
  datasets: { title: "Dataset Registry", description: "Immutable evaluation dataset records and schemas.", icon: Database },
  providers: { title: "Evaluation Providers", description: "AI Governance Control Plane-managed evaluator integrations and capabilities.", icon: ShieldCheck },
};

function providerInstallationTemplate(provider?: ProviderAsset) {
  const schema = provider?.configuration_schema ?? {};
  return {
    displayName: provider ? `${provider.display_name} Production` : "",
    settings: sectionDefaults(schema.settings),
    secretRefs: sectionDefaults(schema.secret_refs) as Record<string, string>,
  };
}

function sectionDefaults(section?: ProviderConfigurationSchema["settings"]) {
  return Object.fromEntries(Object.entries(section?.properties ?? {}).flatMap(([key, field]) => field.default === undefined ? [] : [[key, field.default]]));
}

function readJsonObject(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch { return {}; }
}

function updateJsonField(value: string, key: string, nextValue: unknown) {
  return JSON.stringify({ ...readJsonObject(value), [key]: nextValue }, null, 2);
}

export function AssetRegistryPage({ kind }: { kind: string }) {
  if (!isAssetKind(kind)) return <div className="p-8 text-sm text-destructive">This asset registry does not exist.</div>;
  return <RegistryTable kind={kind} />;
}

function RegistryTable({ kind }: { kind: AssetKind }) {
  const searchParams = useSearchParams();
  const prompts = useQuery({ queryKey: ["asset-registry", "prompts"], queryFn: listPromptAssets, enabled: kind === "prompts" });
  const models = useQuery({ queryKey: ["asset-registry", "models"], queryFn: listModelAssets, enabled: kind === "models" });
  const datasets = useQuery({ queryKey: ["asset-registry", "datasets"], queryFn: listDatasetAssets, enabled: kind === "datasets" });
  const providers = useQuery({ queryKey: ["asset-registry", "providers"], queryFn: listProviderAssets, enabled: kind === "providers" });
  const installations = useQuery({ queryKey: ["provider-installations"], queryFn: listProviderInstallations, enabled: kind === "providers" });
  const info = TITLES[kind];
  const Icon = info.icon;
  const [provenance, setProvenance] = useState<"ALL" | "MANAGED" | "OBSERVED">("ALL");
  const rows = kind === "prompts" ? selectLogicalAssets((prompts.data ?? []).filter((item) => provenance === "ALL" || item.provenance === provenance), (item) => item.name).map((item) => ({ id: item.prompt_id, name: item.name, version: item.version, status: item.status, provenance: item.provenance, details: `${item.variables.length} variables`, updated: item.created_at }))
    : kind === "models" ? selectLogicalAssets((models.data ?? []).filter((item) => provenance === "ALL" || item.provenance === provenance), (item) => `${item.provider}:${item.model_name}`).map((item) => ({ id: item.model_id, name: item.model_name, version: item.version, status: item.status, provenance: item.provenance, details: `${item.provider} · ${item.context_window.toLocaleString()} context`, updated: item.created_at }))
      : kind === "datasets" ? selectLogicalAssets(datasets.data ?? [], (item) => item.name).map((item) => ({ id: item.dataset_id, name: item.name, version: item.version, status: item.status, provenance: item.provenance, details: `${item.record_count.toLocaleString()} records · ${item.schema_version}`, updated: item.created_at }))
        : (providers.data ?? []).map((item) => ({ id: item.name, name: item.display_name, version: item.version, status: "ACTIVE", provenance: "MANAGED" as const, details: `${item.capabilities.supported_metrics.length} metrics`, updated: "" }));
  const loading = prompts.isLoading || models.isLoading || datasets.isLoading || providers.isLoading;
  const failed = prompts.isError || models.isError || datasets.isError || providers.isError;

  const onboardingRegistration = kind === "datasets" && searchParams.get("onboarding") === "register";
  const openProviderInstallation = kind === "providers" && searchParams.get("new") === "1";

  return <div className="studio-page flex flex-col gap-5">
    <Link href="/assets" className="flex w-fit items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Assets</Link>
    <div className="flex items-start gap-3"><div className="rounded-md bg-primary/10 p-2 text-primary"><Icon className="h-5 w-5" /></div><div><h1 className="text-2xl font-semibold">{info.title}</h1><p className="mt-1 text-sm text-muted-foreground">{info.description}</p></div></div>
    <div className="flex justify-end">{kind === "datasets" ? <DatasetUploadForm openInitially={onboardingRegistration} /> : kind === "prompts" || kind === "models" ? <ManagedAssetForm kind={kind} /> : null}</div>
    {kind === "providers" ? <ProviderInstallations providers={providers.data ?? []} installations={installations.data ?? []} loading={loading || installations.isLoading} error={failed || installations.isError} openInitially={openProviderInstallation} /> : <Card><CardContent className="p-0">{kind === "prompts" || kind === "models" ? <div className="flex justify-end border-b p-3"><ProvenanceFilter kind={kind} provenance={provenance} onChange={setProvenance} /></div> : null}{loading ? <div className="p-8 text-sm text-muted-foreground">Loading registry…</div> : failed ? <div className="p-8 text-sm text-destructive">Unable to load this registry.</div> : rows.length === 0 ? <div className="p-10 text-center text-sm text-muted-foreground">No assets have been registered.</div> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b text-muted-foreground"><th className="p-4">Name</th><th>Current Version</th><th>Status</th><th>Provenance</th><th>Registry Details</th><th className="pr-4 text-right">Updated</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id} className="border-b last:border-0 hover:bg-accent/40"><td className="p-4"><Link href={`/assets/${kind}/${encodeURIComponent(row.id)}`} className="font-medium text-primary underline decoration-primary/45 underline-offset-4 transition-colors hover:text-primary/75 hover:decoration-primary">{row.name}</Link></td><td>{row.version}</td><td><StatusBadge status={row.status} /></td><td><AssetProvenanceBadge kind={kind} provenance={row.provenance} /></td><td className="text-muted-foreground">{row.details}</td><td className="pr-4 text-right text-muted-foreground">{row.updated ? new Date(row.updated).toLocaleDateString() : "—"}</td></tr>)}</tbody></table></div>}</CardContent></Card>}
  </div>;
}

function ProvenanceFilter({ kind, provenance, onChange }: { kind: "prompts" | "models"; provenance: "ALL" | "MANAGED" | "OBSERVED"; onChange: (value: "ALL" | "MANAGED" | "OBSERVED") => void }) {
  return <div className="flex gap-1 rounded-md border bg-muted/20 p-1" role="group" aria-label="Filter assets by provenance">{(["ALL", "MANAGED", "OBSERVED"] as const).map((value) => <Button key={value} size="sm" variant={provenance === value ? "secondary" : "ghost"} onClick={() => onChange(value)}>{value === "ALL" ? "All" : value === "MANAGED" ? kind === "models" ? "Registered" : "Managed" : "Observed"}</Button>)}</div>;
}

function ProviderInstallations({ providers, installations, loading, error, openInitially }: { providers: ProviderAsset[]; installations: import("@/lib/api/registries").ProviderInstallation[]; loading: boolean; error: boolean; openInitially: boolean }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(openInitially);
  const [activeTab, setActiveTab] = useState<"configured" | "adapters">("configured");
  const [search, setSearch] = useState("");
  const [providerFilter, setProviderFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [sortBy, setSortBy] = useState<"name" | "provider" | "updated">("updated");
  const [providerType, setProviderType] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [settings, setSettings] = useState("{}");
  const [secretRefs, setSecretRefs] = useState("{}");
  const [enabled, setEnabled] = useState(true);
  const [scope, setScope] = useState<"ORGANIZATION" | "PROJECT">("ORGANIZATION");
  const [formError, setFormError] = useState<string | null>(null);
  const [validationMessage, setValidationMessage] = useState<string | null>(null);
  const [validatedFingerprint, setValidatedFingerprint] = useState<string | null>(null);
  const [inspectedProviderType, setInspectedProviderType] = useState<string | null>(null);
  const [inspectedInstallationId, setInspectedInstallationId] = useState<string | null>(null);
  const [actionsOpenFor, setActionsOpenFor] = useState<string | null>(null);
  const create = useMutation({ mutationFn: createProviderInstallation, onSuccess: async () => { await client.invalidateQueries({ queryKey: ["provider-installations"] }); setOpen(false); setDisplayName(""); setSettings("{}"); setSecretRefs("{}"); setFormError(null); setValidationMessage(null); setValidatedFingerprint(null); }, onError: (reason) => setFormError(reason instanceof Error ? reason.message : "Unable to create provider installation.") });
  const validate = useMutation({ mutationFn: validateProviderInstallation, onSuccess: (result, payload) => { setFormError(null); setValidationMessage(result.message); setValidatedFingerprint(JSON.stringify(payload)); }, onError: (reason) => { setValidationMessage(null); setValidatedFingerprint(null); setFormError(reason instanceof Error ? reason.message : "Provider validation failed."); } });
  const update = useMutation({ mutationFn: ({ installationId, enabled: nextEnabled }: { installationId: string; enabled: boolean }) => updateProviderInstallation(installationId, { enabled: nextEnabled }), onSuccess: () => client.invalidateQueries({ queryKey: ["provider-installations"] }) });

  function applyTemplate(providerType: string) {
    const template = providerInstallationTemplate(providers.find((provider) => provider.name === providerType));
    setProviderType(providerType);
    setDisplayName(template.displayName);
    setSettings(JSON.stringify(template.settings, null, 2));
    setSecretRefs(JSON.stringify(template.secretRefs, null, 2));
    setFormError(null);
    setValidationMessage(null);
    setValidatedFingerprint(null);
  }

  useEffect(() => {
    if (open && !providerType && providers.length) {
      applyTemplate((providers.find((provider) => provider.name === "trulens") ?? providers[0]).name);
    }
  }, [open, providerType, providers]);

  function installationPayload() {
    const parsedSettings = JSON.parse(settings) as Record<string, unknown>;
    const parsedSecretRefs = JSON.parse(secretRefs) as Record<string, string>;
    if (!providerType || !displayName.trim() || Array.isArray(parsedSettings) || Array.isArray(parsedSecretRefs) || !Object.values(parsedSecretRefs).every((value) => typeof value === "string")) throw new Error("Choose a provider type, enter a name, and provide JSON objects with string secret references.");
    return { provider_type: providerType, display_name: displayName.trim(), settings: parsedSettings, secret_refs: parsedSecretRefs, enabled, scope };
  }

  function submit() {
    if (!isCurrentConfigurationValidated) {
      setFormError("Validate Connection before creating this installation.");
      return;
    }
    try {
      setFormError(null);
      create.mutate(installationPayload());
    } catch (reason) { setFormError(reason instanceof Error ? reason.message : "Settings and secret references must be JSON objects."); }
  }

  function validateConnection() {
    try { validate.mutate(installationPayload()); }
    catch (reason) { setValidatedFingerprint(null); setValidationMessage(null); setFormError(reason instanceof Error ? reason.message : "Settings and secret references must be JSON objects."); }
  }

  function validationFingerprint() {
    try { return JSON.stringify(installationPayload()); }
    catch { return null; }
  }

  const currentFingerprint = validationFingerprint();
  const isCurrentConfigurationValidated = currentFingerprint !== null && currentFingerprint === validatedFingerprint;
  const activeInstallations = installations.filter((installation) => installation.enabled).length;
  const visibleInstallations = installations
    .filter((installation) => {
      const query = search.trim().toLowerCase();
      return (!query || [installation.display_name, installation.provider_type, installation.adapter_version].some((value) => value.toLowerCase().includes(query)))
        && (providerFilter === "ALL" || installation.provider_type === providerFilter)
        && (statusFilter === "ALL" || (statusFilter === "ACTIVE" ? installation.enabled : !installation.enabled));
    })
    .sort((left, right) => sortBy === "name"
      ? left.display_name.localeCompare(right.display_name)
      : sortBy === "provider"
        ? left.provider_type.localeCompare(right.provider_type) || left.display_name.localeCompare(right.display_name)
        : new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime());
  const inspectedInstallation = installations.find((installation) => installation.installation_id === inspectedInstallationId);

  return <div className="grid gap-5">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <p className="text-sm text-muted-foreground"><span className="font-medium text-foreground">{providers.length}</span> adapters <span aria-hidden="true">·</span> <span className="font-medium text-foreground">{installations.length}</span> installations <span aria-hidden="true">·</span> <span className="font-medium text-foreground">{activeInstallations}</span> active</p>
      <Button onClick={() => { setOpen(true); applyTemplate((providers.find((provider) => provider.name === "trulens") ?? providers[0])?.name ?? ""); }} disabled={!providers.length}><Plus className="h-4 w-4" />Configure Provider</Button>
    </div>
    <Card><CardContent className="p-0">
      <div className="flex items-center gap-5 border-b border-border/40 px-5" role="tablist" aria-label="Evaluation provider views">
        <button type="button" role="tab" aria-selected={activeTab === "configured"} className={`border-b-2 py-3 text-sm font-medium transition-colors ${activeTab === "configured" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`} onClick={() => setActiveTab("configured")}>Configured <span className="ml-1 text-xs text-muted-foreground">{installations.length}</span></button>
        <button type="button" role="tab" aria-selected={activeTab === "adapters"} className={`border-b-2 py-3 text-sm font-medium transition-colors ${activeTab === "adapters" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`} onClick={() => setActiveTab("adapters")}>Available Adapters <span className="ml-1 text-xs text-muted-foreground">{providers.length}</span></button>
      </div>
      {loading ? <div className="p-8 text-sm text-muted-foreground">Loading evaluation providers…</div> : error ? <div className="p-8 text-sm text-destructive">Unable to load provider configuration.</div> : activeTab === "configured" ? <>
        <div className="flex flex-wrap items-center gap-2 border-b border-border/40 bg-muted/15 p-3">
          <label className="relative min-w-52 flex-1"><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search providers…" aria-label="Search provider installations" /></label>
          <select className="h-9 rounded-md border bg-background px-3 text-sm" aria-label="Filter by provider" value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}><option value="ALL">All providers</option>{providers.map((provider) => <option key={provider.name} value={provider.name}>{provider.display_name}</option>)}</select>
          <select className="h-9 rounded-md border bg-background px-3 text-sm" aria-label="Filter by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="ALL">All statuses</option><option value="ACTIVE">Active</option><option value="DISABLED">Disabled</option></select>
          <select className="h-9 rounded-md border bg-background px-3 text-sm" aria-label="Sort provider installations" value={sortBy} onChange={(event) => setSortBy(event.target.value as "name" | "provider" | "updated")}><option value="updated">Sort: Last updated</option><option value="name">Sort: Name</option><option value="provider">Sort: Provider</option></select>
        </div>
        {!installations.length ? <div className="p-10 text-center text-sm text-muted-foreground">No provider installations exist for this organization or project. Add a provider to configure a shipped adapter.</div> : !visibleInstallations.length ? <div className="p-10 text-center text-sm text-muted-foreground">No installations match these filters.</div> : <div className="overflow-x-auto"><table className="w-full min-w-[900px] text-left text-sm"><thead><tr className="border-b border-border/40 bg-muted/10 text-xs font-medium uppercase tracking-wide text-muted-foreground"><th className="px-5 py-2.5">Name</th><th className="px-3 py-2.5">Provider</th><th className="px-3 py-2.5">Adapter version</th><th className="px-3 py-2.5">Scope</th><th className="px-3 py-2.5">Status</th><th className="px-3 py-2.5">Secrets</th><th className="px-3 py-2.5">Last updated</th><th className="px-5 py-2.5 text-right"><span className="sr-only">Actions</span></th></tr></thead><tbody>{visibleInstallations.map((installation) => <tr key={installation.installation_id} className="border-b border-border/30 last:border-0 hover:bg-accent/35"><td className="px-5 py-3"><button type="button" className="font-medium text-left hover:text-primary hover:underline" onClick={() => setInspectedInstallationId(installation.installation_id)}>{installation.display_name}</button></td><td className="px-3 py-3 text-muted-foreground">{providers.find((provider) => provider.name === installation.provider_type)?.display_name ?? installation.provider_type}</td><td className="px-3 py-3 text-muted-foreground">v{installation.adapter_version}</td><td className="px-3 py-3 text-muted-foreground">{installation.scope === "ORGANIZATION" ? "Organization" : "Project"}</td><td className="px-3 py-3"><StatusBadge status={installation.enabled ? "ACTIVE" : "DISABLED"} /></td><td className="px-3 py-3 text-muted-foreground">{Object.keys(installation.secret_refs).length ? `${Object.keys(installation.secret_refs).length} referenced` : "None"}</td><td className="px-3 py-3 text-muted-foreground">{new Date(installation.updated_at).toLocaleDateString()}</td><td className="relative px-5 py-3 text-right"><Button size="icon" variant="ghost" aria-label={`Actions for ${installation.display_name}`} aria-expanded={actionsOpenFor === installation.installation_id} onClick={() => setActionsOpenFor(actionsOpenFor === installation.installation_id ? null : installation.installation_id)}><MoreHorizontal className="h-4 w-4" /></Button>{actionsOpenFor === installation.installation_id ? <div className="absolute right-5 top-10 z-20 w-36 rounded-md border border-border/50 bg-background p-1 text-left shadow-lg"><button type="button" className="w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent disabled:opacity-50" disabled={update.isPending} onClick={() => { update.mutate({ installationId: installation.installation_id, enabled: !installation.enabled }); setActionsOpenFor(null); }}>{installation.enabled ? "Disable" : "Enable"}</button></div> : null}</td></tr>)}</tbody></table></div>}
      </> : <AdapterCatalog providers={providers} onInspect={setInspectedProviderType} />}
    </CardContent></Card>
    <Sheet open={open} onOpenChange={setOpen}><SheetContent className="overflow-y-auto sm:max-w-2xl"><SheetHeader className="pr-8"><SheetTitle>Add evaluation provider</SheetTitle><p className="text-sm text-muted-foreground">Create a named installation for a shipped evaluation adapter.</p></SheetHeader><div className="mt-6 grid gap-4"><label className="grid gap-1 text-sm">Provider type<select className="h-9 rounded-md border bg-background px-3" value={providerType} onChange={(event) => applyTemplate(event.target.value)}>{providers.map((provider) => <option key={provider.name} value={provider.name}>{provider.display_name}</option>)}</select></label><label className="grid gap-1 text-sm">Installation name<Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label><label className="grid gap-1 text-sm">Scope<select className="h-9 rounded-md border bg-background px-3" value={scope} onChange={(event) => setScope(event.target.value as "ORGANIZATION" | "PROJECT")}><option value="ORGANIZATION">Organization — shared by projects</option><option value="PROJECT">Current project — local variation</option></select><span className="text-xs text-muted-foreground">Use organization scope by default.</span></label><GeneratedConfigurationFields section={providers.find((provider) => provider.name === providerType)?.configuration_schema.settings} value={settings} onChange={setSettings} /><GeneratedConfigurationFields section={providers.find((provider) => provider.name === providerType)?.configuration_schema.secret_refs} value={secretRefs} onChange={setSecretRefs} secretReferences /><details className="grid gap-1 text-sm"><summary className="cursor-pointer font-medium">Advanced JSON</summary><p className="text-xs text-muted-foreground">Use this only for adapter fields not shown above.</p><label className="grid gap-1 text-sm">Settings JSON<textarea className="min-h-28 rounded-md border bg-background p-3 font-mono text-xs" value={settings} onChange={(event) => setSettings(event.target.value)} /></label><label className="mt-3 grid gap-1 text-sm">Secret references JSON<textarea className="min-h-24 rounded-md border bg-background p-3 font-mono text-xs" value={secretRefs} onChange={(event) => setSecretRefs(event.target.value)} /></label></details><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />Enabled <span className="text-xs text-muted-foreground">Enabled installations are always validated by the server.</span></label>{formError ? <p className="text-sm text-destructive">{formError}</p> : null}{validationMessage && isCurrentConfigurationValidated ? <p className="text-sm text-emerald-700 dark:text-emerald-400">{validationMessage}</p> : null}<div className="flex flex-wrap items-center gap-2"><Button variant="outline" disabled={validate.isPending || create.isPending} onClick={validateConnection}>{validate.isPending ? "Validating…" : "Validate connection"}</Button><Button disabled={!isCurrentConfigurationValidated || create.isPending || validate.isPending} onClick={submit}>{create.isPending ? "Creating…" : "Create installation"}</Button>{!isCurrentConfigurationValidated ? <span className="text-xs text-muted-foreground">Validate connection before creating this installation.</span> : null}</div></div></SheetContent></Sheet>
    <Sheet open={Boolean(inspectedProviderType)} onOpenChange={(nextOpen) => { if (!nextOpen) setInspectedProviderType(null); }}><SheetContent className="overflow-y-auto sm:max-w-lg"><ProviderTypeDetails provider={providers.find((provider) => provider.name === inspectedProviderType)} /></SheetContent></Sheet>
    <Sheet open={Boolean(inspectedInstallation)} onOpenChange={(nextOpen) => { if (!nextOpen) setInspectedInstallationId(null); }}><SheetContent className="overflow-y-auto sm:max-w-lg"><ProviderInstallationDetails installation={inspectedInstallation} provider={providers.find((provider) => provider.name === inspectedInstallation?.provider_type)} /></SheetContent></Sheet>
  </div>;
}

function AdapterCatalog({ providers, onInspect }: { providers: ProviderAsset[]; onInspect: (providerName: string) => void }) {
  const openProvider = (providerName: string) => onInspect(providerName);
  return <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left text-sm"><thead><tr className="border-b border-border/40 bg-muted/10 text-xs font-medium uppercase tracking-wide text-muted-foreground"><th className="px-5 py-2.5">Provider</th><th className="px-3 py-2.5">Adapter version</th><th className="px-3 py-2.5">Metrics</th><th className="px-3 py-2.5">Status</th><th className="px-5 py-2.5 text-right"><span className="sr-only">Details</span></th></tr></thead><tbody>{providers.map((provider) => <tr key={provider.name} tabIndex={0} role="link" aria-label={`View ${provider.display_name} adapter details`} className="cursor-pointer border-b border-border/30 last:border-0 hover:bg-accent/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring" onClick={() => openProvider(provider.name)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openProvider(provider.name); } }}><td className="px-5 py-3"><p className="font-medium">{provider.display_name}</p><p className="mt-0.5 text-xs text-muted-foreground">{provider.name}</p></td><td className="px-3 py-3 text-muted-foreground">v{provider.adapter_version}</td><td className="px-3 py-3 text-muted-foreground">{provider.capabilities.supported_metrics.length}</td><td className="px-3 py-3"><StatusBadge status="ACTIVE" /></td><td className="px-5 py-3 text-right"><ChevronRight className="ml-auto h-4 w-4 text-muted-foreground" aria-hidden="true" /></td></tr>)}</tbody></table></div>;
}

function ProviderTypeDetails({ provider }: { provider?: ProviderAsset }) {
  if (!provider) return null;
  const schema = provider.configuration_schema;
  const requiredSecrets = schema.secret_refs?.required ?? [];
  return <><SheetHeader className="pr-8"><SheetTitle>{provider.display_name}</SheetTitle><p className="text-sm text-muted-foreground">Available adapter · v{provider.adapter_version}</p></SheetHeader><div className="mt-6 grid gap-6 text-sm"><div><p className="font-medium">Supported metrics</p><p className="mt-1 leading-6 text-muted-foreground">{provider.capabilities.supported_metrics.join(", ") || "None declared"}</p></div><div><p className="font-medium">Required secret references</p><p className="mt-1 leading-6 text-muted-foreground">{requiredSecrets.length ? requiredSecrets.join(", ") : "None"}</p></div><div><p className="font-medium">Capabilities</p><p className="mt-1 leading-6 text-muted-foreground">{provider.capabilities.supports_batch ? "Batch" : "Single run"} · {provider.capabilities.supports_async ? "Async" : "Synchronous"} · {provider.capabilities.supports_artifacts ? "Artifacts" : "No artifacts"}</p></div><div className="border-t pt-4"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Technical identity</p><p className="mt-2 text-sm text-muted-foreground">Provider key <code className="rounded bg-muted px-1 py-0.5 text-foreground">{provider.name}</code> · Provider version {provider.version}</p></div>{schema.documentation_url ? <Link className="font-medium text-primary hover:underline" href={schema.documentation_url}>Provider documentation →</Link> : null}</div></>;
}

function ProviderInstallationDetails({ installation, provider }: { installation?: import("@/lib/api/registries").ProviderInstallation; provider?: ProviderAsset }) {
  if (!installation) return null;
  return <><SheetHeader className="pr-8"><SheetTitle>{installation.display_name}</SheetTitle><p className="text-sm text-muted-foreground">{provider?.display_name ?? installation.provider_type} · Adapter v{installation.adapter_version}</p></SheetHeader><div className="mt-6 grid gap-6 text-sm"><div className="grid grid-cols-2 gap-4"><div><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Status</p><div className="mt-2"><StatusBadge status={installation.enabled ? "ACTIVE" : "DISABLED"} /></div></div><div><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Scope</p><p className="mt-2">{installation.scope === "ORGANIZATION" ? "Organization" : "Project"}</p></div><div><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Secret references</p><p className="mt-2">{Object.keys(installation.secret_refs).length || "None"}</p></div><div><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Last updated</p><p className="mt-2">{new Date(installation.updated_at).toLocaleString()}</p></div></div><div className="border-t pt-4"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Technical identity</p><p className="mt-2 text-muted-foreground">Installation ID</p><code className="mt-1 block break-all rounded bg-muted p-2 text-xs text-foreground">{installation.installation_id}</code></div></div></>;
}

function GeneratedConfigurationFields({ section, value, onChange, secretReferences = false }: { section?: ProviderConfigurationSchema["settings"]; value: string; onChange: (next: string) => void; secretReferences?: boolean }) {
  const entries = Object.entries(section?.properties ?? {});
  if (!entries.length) return null;
  const current = readJsonObject(value);
  const title = secretReferences ? "Secret references" : "Configuration";
  return <fieldset className="grid gap-3 rounded-md border bg-background/50 p-3 md:col-span-3"><legend className="px-1 text-sm font-medium">{title}</legend>{secretReferences ? <p className="text-xs text-muted-foreground">References only—never paste a key. Local Studio resolves <code>env://OPENAI_API_KEY</code> when a run starts.</p> : <p className="text-xs text-muted-foreground">Adapter-provided defaults are safe to edit and are resolved when the provider runs.</p>}{entries.map(([key, field]) => <GeneratedConfigurationField key={key} name={key} field={field} value={current[key]} onChange={(nextValue) => onChange(updateJsonField(value, key, nextValue))} secretReference={secretReferences} required={section?.required?.includes(key) ?? false} />)}</fieldset>;
}

function GeneratedConfigurationField({ name, field, value, onChange, secretReference, required }: { name: string; field: ProviderConfigurationField; value: unknown; onChange: (next: unknown) => void; secretReference: boolean; required: boolean }) {
  const label = `${field.title ?? name}${required ? " *" : ""}`;
  if (field.type === "array" && field.items?.enum) return <div className="grid gap-1"><span className="text-sm font-medium">{label}</span><span className="text-xs text-muted-foreground">{field.description}</span><div className="flex flex-wrap gap-3">{field.items.enum.map((option) => <label key={option} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Array.isArray(value) && value.includes(option)} onChange={(event) => { const values = new Set(Array.isArray(value) ? value.map(String) : []); if (event.target.checked) values.add(option); else values.delete(option); onChange([...values]); }} />{option}</label>)}</div></div>;
  return <label className="grid gap-1 text-sm"><span>{label}</span>{field.description ? <span className="text-xs text-muted-foreground">{field.description}</span> : null}<Input type={field.type === "integer" || field.type === "number" ? "number" : "text"} value={String(value ?? "")} placeholder={secretReference ? "env://SECRET_NAME" : undefined} onChange={(event) => onChange(field.type === "integer" || field.type === "number" ? Number(event.target.value) : event.target.value)} /></label>;
}
