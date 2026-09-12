"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Filter, Network, Search } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { getDownstream, getNeighbourhood, getUpstream, searchOntologyEntities } from "@/lib/api/graph";
import { AIGovernanceApiError } from "@/lib/api/client";
import type { GraphEntity, GraphRelationship, GraphSubgraph, RelationshipDirection } from "@/types/graph";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EntityDetailPanel } from "./EntityDetailPanel";
import { ENTITY_TYPES, GraphToolbar, MAX_DEPTH, MultiSelect, RELATIONSHIP_TYPES, humanize, type GraphLoadRequest } from "./GraphToolbar";
import { GraphExplorer } from "./GraphExplorer";

type View = "explore" | "technical";
type Selection = { kind: "entity"; entityId: string } | { kind: "relationship"; relationship: GraphRelationship } | null;
type Category = "ALL" | "MODELS" | "DATASETS" | "POLICIES" | "DECISIONS" | "EXPERIMENTS" | "MORE";

const CATEGORIES: { id: Category; label: string; entityTypes: string[] }[] = [
  { id: "ALL", label: "All", entityTypes: [] }, { id: "MODELS", label: "Models", entityTypes: ["Model", "ModelVersion"] }, { id: "DATASETS", label: "Datasets", entityTypes: ["Dataset", "DatasetVersion"] }, { id: "POLICIES", label: "Policies", entityTypes: ["Policy"] }, { id: "DECISIONS", label: "Decisions", entityTypes: ["GovernanceDecision"] }, { id: "EXPERIMENTS", label: "Experiments", entityTypes: ["Experiment", "Candidate", "EvaluationRun"] }, { id: "MORE", label: "More", entityTypes: ["Prompt", "PromptVersion", "Replay", "WorkflowExecution", "Job"] },
];

const emptySubgraph: GraphSubgraph = { nodes: [], edges: [] };

export function GraphWorkspace() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [view, setView] = useState<View>(() => searchParams.get("view") === "technical" ? "technical" : "explore");
  const [request, setRequest] = useState<GraphLoadRequest | null>(() => requestFromSearchParams(searchParams));
  const [selection, setSelection] = useState<Selection>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);

  const graph = useQuery({ queryKey: ["ontology-graph", request], queryFn: () => loadGraph(request), enabled: request !== null });
  const subgraph = graph.data ?? emptySubgraph;
  const selectedEntity = useMemo(() => selection?.kind === "entity" ? subgraph.nodes.find((node) => node.entity.entityId === selection.entityId)?.entity : undefined, [selection, subgraph.nodes]);
  const selectedRelationship = selection?.kind === "relationship" ? selection.relationship : undefined;

  function updateUrl(nextRequest: GraphLoadRequest | null, nextView = view) {
    const params = new URLSearchParams();
    params.set("view", nextView);
    if (nextRequest) { params.set("entityType", nextRequest.entityType); params.set("entityId", nextRequest.entityId); params.set("depth", String(nextRequest.depth)); params.set("direction", nextRequest.direction); nextRequest.relationshipTypes.forEach((type) => params.append("relationshipType", type)); nextRequest.entityTypes.forEach((type) => params.append("nodeType", type)); if (nextRequest.awaitProjection) params.set("awaitProjection", "true"); }
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }
  function load(nextRequest: GraphLoadRequest) { setInspectorOpen(false); setSelection({ kind: "entity", entityId: nextRequest.entityId }); setRequest(nextRequest); updateUrl(nextRequest); }
  function reset() { setInspectorOpen(false); setSelection(null); setRequest(null); updateUrl(null); }
  function changeView(nextView: View) { setView(nextView); updateUrl(request, nextView); }

  return <div className="studio-page flex h-[calc(100vh-4rem)] min-h-0 flex-col gap-4 py-6">
    <header><h1 className="text-2xl font-semibold">Ontology</h1><p className="mt-1 text-sm text-muted-foreground">Explore governed assets, decisions, evidence, and the relationships that connect them.</p></header>
    <div className="flex items-center gap-5 border-b border-border/40" role="tablist" aria-label="Ontology views"><button type="button" role="tab" aria-selected={view === "explore"} className={`border-b-2 py-2.5 text-sm font-medium ${view === "explore" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`} onClick={() => changeView("explore")}>Explore</button><button type="button" role="tab" aria-selected={view === "technical"} className={`border-b-2 py-2.5 text-sm font-medium ${view === "technical" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`} onClick={() => changeView("technical")}>Technical</button></div>
    {view === "explore" ? <ExploreControls request={request} disabled={graph.isFetching} onLoad={load} /> : <GraphToolbar key={request ? requestKey(request) : "empty"} disabled={graph.isFetching} request={request} onLoad={load} onReset={reset} />}
    {request && view === "explore" ? <ExploreFilters request={request} disabled={graph.isFetching} onChange={load} /> : null}
    {request && view === "explore" ? <ExploreSummary request={request} subgraph={subgraph} /> : null}
    <section className="relative min-h-0 flex-1 overflow-hidden rounded-lg border border-border/40 bg-card">
      {graph.isError ? <GraphError error={graph.error} /> : null}
      {graph.isFetching ? <div className="absolute left-4 top-4 z-10 rounded-md border border-border/50 bg-card px-3 py-2 text-sm shadow-sm">Loading graph data…</div> : null}
      {!request ? <ExploreEmpty /> : <GraphExplorer subgraph={subgraph} presentation={view} onSelectEntity={(entityId) => { setInspectorOpen(false); setSelection({ kind: "entity", entityId }); }} onInspectEntity={(entityId) => { setSelection({ kind: "entity", entityId }); setInspectorOpen(true); }} onSelectRelationship={(relationship) => { setInspectorOpen(false); setSelection({ kind: "relationship", relationship }); }} onInspectRelationship={(relationship) => { setSelection({ kind: "relationship", relationship }); setInspectorOpen(true); }} />}
      {view === "explore" && selectedEntity ? <div className="absolute bottom-4 left-4 z-10 flex items-center gap-2 rounded-md border border-border/50 bg-card px-2 py-1.5 shadow-sm"><span className="max-w-48 truncate px-1 text-sm font-medium">{entityName(selectedEntity)}</span><Button size="sm" variant="ghost" onClick={() => load({ ...request!, entityType: selectedEntity.entityType, entityId: selectedEntity.entityId, depth: 1 })}>Explore from here</Button><Button size="sm" variant="outline" onClick={() => setInspectorOpen(true)}>Inspect</Button>{request!.depth < MAX_DEPTH ? <Button size="sm" variant="ghost" onClick={() => load({ ...request!, depth: request!.depth + 1 })}>Expand one hop</Button> : null}</div> : null}
    </section>
    <EntityDetailPanel entity={selectedEntity} relationship={selectedRelationship} technical={view === "technical"} open={inspectorOpen} onOpenChange={setInspectorOpen} />
  </div>;
}

function ExploreControls({ request, disabled, onLoad }: { request: GraphLoadRequest | null; disabled: boolean; onLoad: (request: GraphLoadRequest) => void }) {
  const [query, setQuery] = useState(""); const [debouncedQuery, setDebouncedQuery] = useState(""); const [category, setCategory] = useState<Category>("ALL");
  const categoryTypes = CATEGORIES.find((item) => item.id === category)?.entityTypes ?? [];
  useEffect(() => { const timeout = window.setTimeout(() => setDebouncedQuery(query.trim()), 280); return () => window.clearTimeout(timeout); }, [query]);
  const results = useQuery({ queryKey: ["ontology-entity-search", debouncedQuery, categoryTypes], queryFn: () => searchOntologyEntities(debouncedQuery, categoryTypes, 15), enabled: debouncedQuery.length >= 2 });
  const groups = groupSearchResults(results.data?.items ?? []);
  return <div className="relative"><label className="relative block"><Search className="pointer-events-none absolute left-4 top-3 h-5 w-5 text-muted-foreground" /><Input disabled={disabled} className="h-11 pl-11 text-sm" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search models, datasets, policies, prompts, decisions, executions…" aria-label="Search ontology entities" /></label><div className="mt-2 flex flex-wrap gap-1.5">{CATEGORIES.map((item) => <Button key={item.id} size="sm" variant={category === item.id ? "secondary" : "ghost"} disabled={disabled} onClick={() => setCategory(item.id)}>{item.label}</Button>)}</div>{results.isError ? <p role="alert" className="mt-2 text-sm text-destructive">Unable to search ontology entities.</p> : null}{query.trim().length >= 2 ? <div className="mt-2 max-h-64 overflow-y-auto rounded-md border border-border/40 bg-card shadow-sm">{results.isLoading || query.trim() !== debouncedQuery ? <p className="p-3 text-sm text-muted-foreground">Searching entities…</p> : groups.length ? groups.map(([type, entities]) => <div key={type} className="border-b border-border/30 last:border-0"><p className="px-4 pt-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">{humanize(type)}</p>{entities.map((entity) => <button key={`${entity.entityType}/${entity.entityId}`} type="button" className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-accent/35" onClick={() => { onLoad({ entityType: entity.entityType, entityId: entity.entityId, depth: request?.depth ?? 1, direction: request?.direction ?? "both", relationshipTypes: request?.relationshipTypes ?? [], entityTypes: request?.entityTypes ?? [] }); setQuery(""); }}><span><span className="font-medium">{entityName(entity)}</span><span className="ml-2 text-xs text-muted-foreground">{entity.entityId}</span></span><span className="text-xs text-muted-foreground">{entity.lifecycle}</span></button>)}</div>) : <p className="p-3 text-sm text-muted-foreground">No matching entities. Try a different name or category.</p>}</div> : null}</div>;
}

function ExploreFilters({ request, disabled, onChange }: { request: GraphLoadRequest; disabled: boolean; onChange: (request: GraphLoadRequest) => void }) {
  const [open, setOpen] = useState(false); const update = (changes: Partial<GraphLoadRequest>) => onChange({ ...request, ...changes });
  return <div><Button size="sm" variant="outline" onClick={() => setOpen(!open)}><Filter className="h-4 w-4" />Filters</Button>{open ? <div className="mt-2 grid gap-3 rounded-lg border border-border/40 bg-muted/10 p-3 md:grid-cols-4"><label className="grid gap-1 text-xs font-medium text-muted-foreground">Depth<select disabled={disabled} className="h-9 rounded-md border bg-background px-3 text-sm text-foreground" value={request.depth} onChange={(event) => update({ depth: Number(event.target.value) })}>{[1, 2, 3, 4, 5].map((depth) => <option key={depth} value={depth}>{depth} hop{depth === 1 ? "" : "s"}</option>)}</select></label><label className="grid gap-1 text-xs font-medium text-muted-foreground">Direction<select disabled={disabled} className="h-9 rounded-md border bg-background px-3 text-sm text-foreground" value={request.direction} onChange={(event) => update({ direction: event.target.value as RelationshipDirection })}><option value="both">Both directions</option><option value="incoming">Upstream</option><option value="outgoing">Downstream</option></select></label><MultiSelect label="Relationship types" options={RELATIONSHIP_TYPES} value={request.relationshipTypes} onChange={(relationshipTypes) => update({ relationshipTypes })} /><MultiSelect label="Node types" options={ENTITY_TYPES} value={request.entityTypes} onChange={(entityTypes) => update({ entityTypes })} /></div> : null}</div>;
}

function ExploreSummary({ request, subgraph }: { request: GraphLoadRequest; subgraph: GraphSubgraph }) { const root = subgraph.nodes.find((node) => node.depth === 0)?.entity; const groups = new Map<string, number>(); subgraph.nodes.filter((node) => node.depth > 0).forEach((node) => groups.set(node.entity.entityType, (groups.get(node.entity.entityType) ?? 0) + 1)); return <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm"><div><span className="font-medium">{root ? entityName(root) : request.entityId}</span><span className="ml-2 text-muted-foreground">{root ? humanize(root.entityType) : humanize(request.entityType)}</span></div>{[...groups.entries()].slice(0, 6).map(([type, count]) => <span key={type} className="text-muted-foreground">{count} {humanize(type)}{count === 1 ? "" : "s"}</span>)}</div>; }
function groupSearchResults(entities: GraphEntity[]) { const groups = new Map<string, GraphEntity[]>(); entities.forEach((entity) => groups.set(entity.entityType, [...(groups.get(entity.entityType) ?? []), entity])); return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right)); }
function ExploreEmpty() { return <div className="flex h-full flex-col items-center justify-center px-6 text-center"><Network className="h-8 w-8 text-primary/70" /><h2 className="mt-4 font-semibold">Start with an entity</h2><p className="mt-1 max-w-md text-sm text-muted-foreground">Search above for a model, dataset, policy, decision, prompt, or execution to see its governed context and relationships.</p></div>; }
function GraphError({ error }: { error: Error }) { const message = error instanceof AIGovernanceApiError ? `${error.code}: ${error.message}` : error.message; return <div role="alert" className="absolute left-4 right-4 top-4 z-10 flex items-start gap-2 rounded-md border border-destructive/30 bg-card px-3 py-2 text-sm text-destructive shadow-sm"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />{message}</div>; }
function entityName(entity: GraphEntity) { const values = [entity.immutableAttributes.name, entity.immutableAttributes.display_name, entity.immutableAttributes.model_name, entity.metadata.label, entity.metadata.name]; return values.find((value): value is string => typeof value === "string" && Boolean(value.trim())) ?? entity.entityId; }
function requestFromSearchParams(searchParams: ReturnType<typeof useSearchParams>): GraphLoadRequest | null { const entityType = searchParams.get("entityType")?.trim(); const entityId = searchParams.get("entityId")?.trim(); if (!entityType || !entityId) return null; const depth = Number(searchParams.get("depth") ?? "1"); const direction = searchParams.get("direction"); return { entityType, entityId, depth: Math.min(Math.max(Number.isFinite(depth) ? depth : 1, 1), MAX_DEPTH), direction: direction === "incoming" || direction === "outgoing" ? direction : "both", relationshipTypes: searchParams.getAll("relationshipType"), entityTypes: searchParams.getAll("nodeType"), awaitProjection: searchParams.get("awaitProjection") === "true" }; }
function requestKey(request: GraphLoadRequest) { return [request.entityType, request.entityId, request.depth, request.direction, request.relationshipTypes.join(","), request.entityTypes.join(",")].join("|"); }
async function loadGraph(request: GraphLoadRequest | null) { if (!request) return emptySubgraph; const shared = { entityType: request.entityType, entityId: request.entityId, depth: request.depth, relationshipTypes: request.relationshipTypes, limit: 100 }; if (request.direction === "incoming") return getUpstream(shared); if (request.direction === "outgoing") return getDownstream(shared); return getNeighbourhood({ ...shared, entityTypes: request.entityTypes }); }
