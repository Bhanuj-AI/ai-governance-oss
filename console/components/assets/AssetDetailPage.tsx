"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, GitBranch, History, Network, PackageSearch, ScrollText } from "lucide-react";
import { useState } from "react";
import { AssetProvenanceBadge, StatusBadge } from "@/components/assets/AssetsPage";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getNeighbourhood, getRelationships } from "@/lib/api/graph";
import { listOntologySyncEvents } from "@/lib/api/ontology-sync";
import {
  getPromptVersion,
  listDatasetAssets,
  listModelAssets,
  listPromptAssets,
  listPromptVersions,
  listProviderAssets,
  type DatasetAsset,
  type ModelAsset,
  type PromptAsset,
  type ProviderAsset,
} from "@/lib/api/registries";
import type { GraphEntity, GraphRelationship } from "@/types/graph";

const TABS = ["Overview", "Versions", "References", "Lineage", "Audit History"] as const;
type Tab = (typeof TABS)[number];
type AssetKind = "prompts" | "models" | "datasets" | "providers";

const ONTOLOGY_TYPES: Record<AssetKind, string> = {
  prompts: "PromptVersion",
  models: "ModelVersion",
  datasets: "DatasetVersion",
  providers: "EvaluationProvider",
};

export function AssetDetailPage({ kind, assetId }: { kind: string; assetId: string }) {
  const registryKind = isAssetKind(kind) ? kind : null;
  const [tab, setTab] = useState<Tab>("Overview");
  const [selectedVersionId, setSelectedVersionId] = useState(assetId);
  const prompts = useQuery({ queryKey: ["asset-registry", "prompts"], queryFn: listPromptAssets, enabled: registryKind === "prompts" });
  const models = useQuery({ queryKey: ["asset-registry", "models"], queryFn: listModelAssets, enabled: registryKind === "models" });
  const datasets = useQuery({ queryKey: ["asset-registry", "datasets"], queryFn: listDatasetAssets, enabled: registryKind === "datasets" });
  const providers = useQuery({ queryKey: ["asset-registry", "providers"], queryFn: listProviderAssets, enabled: registryKind === "providers" });

  const asset = registryKind === "prompts" ? prompts.data?.find((item) => item.prompt_id === assetId)
    : registryKind === "models" ? models.data?.find((item) => item.model_id === assetId)
      : registryKind === "datasets" ? datasets.data?.find((item) => item.dataset_id === assetId)
        : registryKind === "providers" ? providers.data?.find((item) => item.name === assetId) : undefined;

  const promptVersions = useQuery({
    queryKey: ["asset-versions", "prompts", (asset as PromptAsset | undefined)?.name],
    queryFn: () => listPromptVersions((asset as PromptAsset).name),
    enabled: registryKind === "prompts" && Boolean(asset),
  });
  const promptContent = useQuery({
    queryKey: ["prompt-content", selectedVersionId],
    queryFn: () => getPromptVersion(selectedVersionId),
    enabled: registryKind === "prompts" && Boolean(selectedVersionId),
  });

  if (!registryKind) return <MissingAsset />;
  const loading = prompts.isLoading || models.isLoading || datasets.isLoading || providers.isLoading;
  if (loading) return <div className="p-8 text-sm text-muted-foreground">Loading asset…</div>;
  if (!asset) return <MissingAsset />;

  const versions = versionsFor(registryKind, asset, models.data ?? [], datasets.data ?? [], promptVersions.data ?? []);
  const selected = versions.find((item) => versionId(registryKind, item) === selectedVersionId) ?? asset;
  const entityType = ONTOLOGY_TYPES[registryKind];
  const entityId = versionId(registryKind, selected);

  return (
    <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-5 px-6 py-5">
      <Link href="/assets" className="flex w-fit items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Assets</Link>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2"><h1 className="text-2xl font-semibold">{assetName(registryKind, asset)}</h1><AssetProvenanceBadge kind={registryKind} provenance={assetProvenance(registryKind, selected)} /><StatusBadge status={assetStatus(registryKind, selected)} /></div>
          <p className="mt-1 text-sm text-muted-foreground">{assetSubtitle(registryKind, asset)}</p>
          <code className="mt-2 block text-xs text-muted-foreground">{entityId}</code>
        </div>
        <Link href={`/graph?entityType=${encodeURIComponent(entityType)}&entityId=${encodeURIComponent(entityId)}&depth=3`} className="inline-flex h-9 items-center gap-2 rounded-md border bg-background px-3 text-sm font-medium shadow-sm hover:bg-accent"><Network className="h-4 w-4" />Open Ontology</Link>
      </header>
      <div className="flex gap-1 overflow-x-auto border-b">
        {TABS.map((item) => <button key={item} className={`shrink-0 px-3 py-2 text-sm ${tab === item ? "border-b-2 border-primary font-medium" : "text-muted-foreground hover:text-foreground"}`} onClick={() => setTab(item)}>{item}</button>)}
      </div>
      {tab === "Overview" ? <Overview kind={registryKind} asset={selected} promptTemplate={promptContent.data?.template} /> : null}
      {tab === "Versions" ? <Versions kind={registryKind} versions={versions} selectedVersionId={selectedVersionId} onSelect={setSelectedVersionId} /> : null}
      {tab === "References" ? <References entityType={entityType} entityId={entityId} /> : null}
      {tab === "Lineage" ? <Lineage entityType={entityType} entityId={entityId} name={assetName(registryKind, selected)} /> : null}
      {tab === "Audit History" ? <AuditHistory entityType={entityType} entityId={entityId} /> : null}
    </div>
  );
}

function Overview({ kind, asset, promptTemplate }: { kind: AssetKind; asset: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset; promptTemplate?: string | null }) {
  const rows = commonRows(kind, asset);
  return <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.7fr)]">
    <Card><CardHeader><CardTitle>Overview</CardTitle><CardDescription>Governed metadata for this selected asset version.</CardDescription></CardHeader><CardContent><dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">{rows.map(([label, value]) => <div key={label}><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 break-words text-sm">{value}</dd></div>)}</dl></CardContent></Card>
    <Card><CardHeader><CardTitle>{kind === "prompts" ? "Observed Configuration" : kind === "models" ? "Observed Runtime Configuration" : kind === "datasets" ? "Schema Preview" : "Provider Configuration"}</CardTitle><CardDescription>{kind === "datasets" ? "Schema fields are registered separately from the dataset storage location." : kind === "prompts" || kind === "models" ? "Captured from governed execution evidence; Kavach does not author runtime configuration." : "Versioned configuration recorded by the registry."}</CardDescription></CardHeader><CardContent>{configuration(kind, asset, promptTemplate)}</CardContent></Card>
  </div>;
}

function Versions({ kind, versions, selectedVersionId, onSelect }: { kind: AssetKind; versions: (PromptAsset | ModelAsset | DatasetAsset | ProviderAsset)[]; selectedVersionId: string; onSelect: (value: string) => void }) {
  return <Card><CardHeader><CardTitle>Versions</CardTitle><CardDescription>Select a version to inspect its immutable registry metadata and lineage.</CardDescription></CardHeader><CardContent><div className="divide-y rounded-md border">{[...versions].sort(sortVersionRows).map((version) => { const id = versionId(kind, version); return <button key={id} className={`flex w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-accent/50 ${id === selectedVersionId ? "bg-accent/60" : ""}`} onClick={() => onSelect(id)}><div><div className="font-medium">{version.version}</div><div className="mt-1 text-xs text-muted-foreground">{versionCreator(kind, version)} · {formatDate(versionCreatedAt(kind, version))}</div></div><StatusBadge status={assetStatus(kind, version)} /></button>; })}</div></CardContent></Card>;
}

function References({ entityType, entityId }: { entityType: string; entityId: string }) {
  const query = useQuery({ queryKey: ["asset-references", entityType, entityId], queryFn: () => getRelationships({ entityType, entityId, direction: "both", limit: 100 }) });
  if (query.isLoading) return <Loading label="Loading references…" />;
  if (query.isError) return <Empty title="References unavailable" description="This asset has not been synchronized to the ontology yet." icon={PackageSearch} />;
  const groups = groupReferences(query.data?.items ?? [], entityId);
  return <Card><CardHeader><CardTitle>References</CardTitle><CardDescription>Direct governed relationships for this exact asset version.</CardDescription></CardHeader><CardContent>{groups.length === 0 ? <Empty title="No references" description="This version is not yet referenced by another governed record." icon={PackageSearch} /> : <div className="grid gap-3 sm:grid-cols-2">{groups.map(([type, references]) => <div key={type} className="rounded-md border p-3"><div className="flex items-center justify-between gap-2"><span className="font-medium">{humanize(type)}</span><Badge variant="secondary">{references.length}</Badge></div><div className="mt-2 space-y-1.5">{references.slice(0, 4).map((reference) => <div key={reference.id} className="truncate text-sm text-muted-foreground" title={reference.id}>{reference.id}</div>)}{references.length > 4 ? <div className="text-xs text-muted-foreground">+{references.length - 4} more</div> : null}</div></div>)}</div>}</CardContent></Card>;
}

function Lineage({ entityType, entityId, name }: { entityType: string; entityId: string; name: string }) {
  const query = useQuery({ queryKey: ["asset-lineage", entityType, entityId], queryFn: () => getNeighbourhood({ entityType, entityId, depth: 3, limit: 80 }) });
  if (query.isLoading) return <Loading label="Loading lineage…" />;
  if (query.isError) return <Empty title="Lineage unavailable" description="This asset has not been synchronized to the ontology yet." icon={GitBranch} />;
  const nodes = query.data?.nodes ?? [];
  const steps = lineageSteps(nodes.map((node) => node.entity), entityId);
  return <Card><CardHeader><CardTitle>Lineage</CardTitle><CardDescription>Bounded ontology neighbourhood for this version. It shows governed context, not operational analytics.</CardDescription></CardHeader><CardContent><div className="space-y-0"><LineageStep label={name} detail="Selected asset version" root />{steps.length === 0 ? <div className="ml-5 border-l pl-6 py-4 text-sm text-muted-foreground">No downstream or upstream governed records are connected yet.</div> : steps.map(([type, entities]) => <LineageStep key={type} label={`${humanize(type)} (${entities.length})`} detail={entities.slice(0, 3).map(entityLabel).join(" · ")} />)}</div></CardContent></Card>;
}

function AuditHistory({ entityType, entityId }: { entityType: string; entityId: string }) {
  const query = useQuery({ queryKey: ["asset-audit", entityType, entityId], queryFn: () => listOntologySyncEvents({ entityType, entityId }) });
  if (query.isLoading) return <Loading label="Loading audit history…" />;
  if (query.isError) return <Empty title="Audit history unavailable" description="No lifecycle synchronization records could be loaded for this version." icon={ScrollText} />;
  const events = [...(query.data ?? [])].sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime());
  return <Card><CardHeader><CardTitle>Audit History</CardTitle><CardDescription>Registry lifecycle events recorded for this exact version.</CardDescription></CardHeader><CardContent>{events.length === 0 ? <Empty title="No recorded lifecycle events" description="New lifecycle events will appear here as this asset is registered or changes state." icon={History} /> : <div className="divide-y rounded-md border">{events.map((event) => <div key={event.eventId} className="flex items-start justify-between gap-4 p-4"><div><div className="font-medium">{humanize(event.eventType)}</div><div className="mt-1 text-sm text-muted-foreground">{event.status} · {event.scopeIdentifier ?? "Registry"}</div></div><time className="shrink-0 text-xs text-muted-foreground">{formatDate(event.createdAt)}</time></div>)}</div>}</CardContent></Card>;
}

function configuration(kind: AssetKind, asset: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset, promptTemplate?: string | null) {
  if (kind === "prompts") { const prompt = asset as PromptAsset; return <div className="space-y-3"><MetadataList rows={[["Variables", prompt.variables.join(", ") || "None"], ["Source system", prompt.source_system ?? "Not recorded"], ["Content hash", prompt.content_hash ?? "Not recorded"]]} /><div><div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Prompt content</div><pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-3 text-xs">{prompt.content_available ? (promptTemplate ?? "Loading protected prompt content…") : "Prompt content unavailable. Producer submitted only metadata."}</pre></div></div>; }
  if (kind === "models") { const model = asset as ModelAsset; const parameterRows: [string, string][] = Object.entries(model.parameters).map(([key, value]) => [humanize(key), renderValue(value)]); return <MetadataList rows={[["Source system", model.source_system ?? "Not recorded"], ["Source reference", model.source_reference ?? "Not recorded"], ["Context window", model.context_window.toLocaleString()], ...parameterRows]} />; }
  if (kind === "datasets") { const dataset = asset as DatasetAsset; return <MetadataList rows={[["Schema version", dataset.schema_version], ["Storage type", dataset.storage_type], ["Records", dataset.record_count.toLocaleString()], ["Checksum", dataset.checksum], ["Fields", "No field-level schema has been registered."]]} />; }
  const provider = asset as ProviderAsset;
  return <MetadataList rows={[["Adapter version", provider.adapter_version], ["Config schema", provider.config_schema_version], ["Metrics", provider.capabilities.supported_metrics.join(", ") || "None"], ["Modes", provider.capabilities.supported_evaluation_modes.join(", ") || "Default"]]} />;
}

function MetadataList({ rows }: { rows: [string, string][] }) { return <dl className="space-y-3">{rows.map(([label, value]) => <div key={label}><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 break-words text-sm">{value}</dd></div>)}</dl>; }
function Loading({ label }: { label: string }) { return <div className="p-8 text-sm text-muted-foreground">{label}</div>; }
function Empty({ title, description, icon: Icon }: { title: string; description: string; icon: typeof PackageSearch }) { return <div className="flex min-h-40 flex-col items-center justify-center gap-2 rounded-md border border-dashed p-6 text-center"><Icon className="h-5 w-5 text-muted-foreground" /><div className="font-medium">{title}</div><p className="max-w-md text-sm text-muted-foreground">{description}</p></div>; }
function MissingAsset() { return <div className="p-8 text-sm text-destructive">This asset does not exist or is not available in the selected project.</div>; }
function LineageStep({ label, detail, root = false }: { label: string; detail: string; root?: boolean }) { return <div className="relative flex gap-3 pb-4 last:pb-0"><div className="flex w-10 flex-col items-center"><div className={`z-10 h-3 w-3 rounded-full ${root ? "bg-primary" : "bg-muted-foreground/50"}`} />{!root ? null : <div className="absolute top-3 h-5 w-px bg-border" />}</div><div className="pb-1"><div className="text-sm font-medium">{label}</div><div className="mt-0.5 max-w-2xl text-xs text-muted-foreground">{detail}</div></div></div>; }

function isAssetKind(value: string): value is AssetKind { return ["prompts", "models", "datasets", "providers"].includes(value); }
function versionsFor(kind: AssetKind, asset: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset, models: ModelAsset[], datasets: DatasetAsset[], prompts: PromptAsset[]) { if (kind === "prompts") return prompts; if (kind === "models") { const model = asset as ModelAsset; return models.filter((item) => item.provider === model.provider && item.model_name === model.model_name); } if (kind === "datasets") return datasets.filter((item) => item.name === (asset as DatasetAsset).name); return [asset]; }
function versionId(kind: AssetKind, asset: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset) { return kind === "prompts" ? (asset as PromptAsset).prompt_id : kind === "models" ? (asset as ModelAsset).model_id : kind === "datasets" ? (asset as DatasetAsset).dataset_id : (asset as ProviderAsset).name; }
function assetName(kind: AssetKind, asset: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset) { return kind === "prompts" ? (asset as PromptAsset).name : kind === "models" ? (asset as ModelAsset).model_name : kind === "datasets" ? (asset as DatasetAsset).name : (asset as ProviderAsset).display_name; }
function assetSubtitle(kind: AssetKind, asset: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset) { const provenance = assetProvenance(kind, asset).toLowerCase(); return kind === "models" ? `${provenance} model · ${(asset as ModelAsset).provider}` : kind === "providers" ? "Managed evaluation provider" : kind === "prompts" ? `${provenance} prompt identity` : `${provenance} dataset registry`; }
function assetProvenance(kind: AssetKind, asset: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset): "MANAGED" | "OBSERVED" | "IMPORTED" { if (kind === "providers") return "MANAGED"; return (asset as PromptAsset | ModelAsset | DatasetAsset).provenance; }
function assetStatus(kind: AssetKind, asset: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset) { return kind === "providers" ? "ACTIVE" : (asset as PromptAsset | ModelAsset | DatasetAsset).status; }
function versionCreator(kind: AssetKind, asset: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset) { return kind === "prompts" ? (asset as PromptAsset).created_by : kind === "models" ? (asset as ModelAsset).creator : kind === "datasets" ? (asset as DatasetAsset).creator : "Provider registry"; }
function versionCreatedAt(kind: AssetKind, asset: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset) { return kind === "providers" ? "" : (asset as PromptAsset | ModelAsset | DatasetAsset).created_at; }
function commonRows(kind: AssetKind, asset: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset): [string, string][] { const rows: [string, string][] = [["Version", asset.version], ["Status", assetStatus(kind, asset)], ["Provenance", assetProvenance(kind, asset)], ["Owner", versionCreator(kind, asset)]]; if (kind !== "providers") { const source = (asset as PromptAsset | ModelAsset | DatasetAsset).source_system; if (source) rows.push(["Source system", source]); rows.push(["Registered", formatDate(versionCreatedAt(kind, asset))]); } if (kind === "prompts") rows.push(["Variables", String((asset as PromptAsset).variables.length)]); if (kind === "models") rows.push(["Provider", (asset as ModelAsset).provider]); if (kind === "datasets") rows.push(["Description", (asset as DatasetAsset).description]); if (kind === "providers") rows.push(["Metrics supported", String((asset as ProviderAsset).capabilities.supported_metrics.length)]); return rows; }
function groupReferences(items: GraphRelationship[], entityId: string) { const groups = new Map<string, Map<string, { id: string }>>(); items.forEach((item) => { const type = item.sourceEntityId === entityId ? item.targetEntityType : item.sourceEntityType; const id = item.sourceEntityId === entityId ? item.targetEntityId : item.sourceEntityId; if (type === "Actor" || id === entityId) return; const references = groups.get(type) ?? new Map<string, { id: string }>(); references.set(id, { id }); groups.set(type, references); }); return [...groups.entries()].map(([type, references]) => [type, [...references.values()]] as [string, { id: string }[]]).sort(([left], [right]) => left.localeCompare(right)); }
function lineageSteps(entities: GraphEntity[], rootId: string) { const groups = new Map<string, GraphEntity[]>(); entities.filter((entity) => entity.entityId !== rootId && entity.entityType !== "Actor").forEach((entity) => groups.set(entity.entityType, [...(groups.get(entity.entityType) ?? []), entity])); return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right)); }
function entityLabel(entity: GraphEntity) { const name = entity.immutableAttributes.name ?? entity.immutableAttributes.model_name ?? entity.metadata.label; return typeof name === "string" ? name : entity.entityId; }
function humanize(value: string) { return value.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").replace(/\b\w/g, (character) => character.toUpperCase()); }
function renderValue(value: unknown) { return typeof value === "string" ? value : JSON.stringify(value); }
function formatDate(value: string) { return value ? new Date(value).toLocaleString() : "Not recorded"; }
function sortVersionRows(left: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset, right: PromptAsset | ModelAsset | DatasetAsset | ProviderAsset) { const leftDate = "created_at" in left ? new Date(left.created_at).getTime() : 0; const rightDate = "created_at" in right ? new Date(right.created_at).getTime() : 0; return rightDate - leftDate || right.version.localeCompare(left.version, undefined, { numeric: true }); }
