"use client";

import { RotateCcw, Search } from "lucide-react";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { RelationshipDirection } from "@/types/graph";

export type GraphLoadRequest = { entityType: string; entityId: string; depth: number; direction: RelationshipDirection; relationshipTypes: string[]; entityTypes: string[]; awaitProjection?: boolean };

export const MAX_DEPTH = 5;
export const ENTITY_TYPES = ["Actor", "Prompt", "PromptVersion", "Model", "ModelVersion", "Dataset", "DatasetVersion", "EvaluationProvider", "Experiment", "Candidate", "EvaluationRun", "EvaluationResult", "Metric", "EvaluationArtifact", "EvaluationHistory", "EvaluationComparison", "DriftAnalysis", "Leaderboard", "LeaderboardEntry", "GovernanceDecision", "Policy", "Job", "MCPAuditRecord", "WorkflowExecution", "ReplayInvestigation", "Replay", "ReplayResult", "GovernanceInsight", "GovernanceReport"];
export const RELATIONSHIP_TYPES = ["HAS_VERSION", "VERSION_OF", "SUPERSEDES", "OWNED_BY", "CREATED_BY", "HAS_CANDIDATE", "PARTICIPATES_IN", "USES", "EVALUATED_BY", "HAS_RUN", "EXECUTES", "PRODUCES", "HAS_METRIC", "HAS_ARTIFACT", "RECORDED_IN", "COMPARED_WITH", "GENERATES", "CAUSED_DRIFT", "RANKED_BY", "HAS_ENTRY", "RANKS", "RECOMMENDS", "GENERATED_FROM", "DECIDES_ON", "APPROVED_BY", "REJECTED_BY", "BLOCKED_BY", "GOVERNED_BY", "SUBMITTED_AS", "RESULTED_IN", "AUDITED_BY", "REFERENCES_RESOURCE", "REPLAY_OF", "RECONSTRUCTS", "OBSERVED_BY", "INVESTIGATES"];

export function GraphToolbar({ disabled, request, onLoad, onReset }: { disabled?: boolean; request: GraphLoadRequest | null; onLoad: (request: GraphLoadRequest) => void; onReset: () => void }) {
  const [entityType, setEntityType] = useState(request?.entityType ?? "Candidate");
  const [entityId, setEntityId] = useState(request?.entityId ?? "");
  const [depth, setDepth] = useState(request?.depth ?? 2);
  const [direction, setDirection] = useState<RelationshipDirection>(request?.direction ?? "both");
  const [relationshipTypes, setRelationshipTypes] = useState(request?.relationshipTypes ?? []);
  const [entityTypes, setEntityTypes] = useState(request?.entityTypes ?? []);

  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); onLoad({ entityType, entityId: entityId.trim(), depth: Math.min(Math.max(depth, 1), MAX_DEPTH), direction, relationshipTypes, entityTypes }); }
  function reset() { setEntityType("Candidate"); setEntityId(""); setDepth(2); setDirection("both"); setRelationshipTypes([]); setEntityTypes([]); onReset(); }

  return <form className="grid gap-3 rounded-lg border border-border/50 bg-card p-4 xl:grid-cols-[minmax(180px,0.8fr)_minmax(240px,1.3fr)_100px_150px_minmax(180px,1fr)_minmax(180px,1fr)_auto] xl:items-end" onSubmit={submit}>
    <label className="grid gap-1 text-xs font-medium text-muted-foreground">Entity type<select className="h-9 rounded-md border bg-background px-3 text-sm text-foreground" value={entityType} onChange={(event) => setEntityType(event.target.value)}>{ENTITY_TYPES.map((type) => <option key={type}>{type}</option>)}</select></label>
    <label className="grid gap-1 text-xs font-medium text-muted-foreground">Entity ID<Input value={entityId} onChange={(event) => setEntityId(event.target.value)} placeholder="Exact ontology identifier" required /></label>
    <label className="grid gap-1 text-xs font-medium text-muted-foreground">Depth<Input type="number" min={1} max={MAX_DEPTH} value={depth} onChange={(event) => setDepth(Number(event.target.value))} /></label>
    <label className="grid gap-1 text-xs font-medium text-muted-foreground">Direction<select className="h-9 rounded-md border bg-background px-3 text-sm text-foreground" value={direction} onChange={(event) => setDirection(event.target.value as RelationshipDirection)}><option value="both">Both</option><option value="incoming">Incoming</option><option value="outgoing">Outgoing</option></select></label>
    <MultiSelect label="Relationship types" options={RELATIONSHIP_TYPES} value={relationshipTypes} onChange={setRelationshipTypes} />
    <MultiSelect label="Node types" options={ENTITY_TYPES} value={entityTypes} onChange={setEntityTypes} />
    <div className="flex gap-2"><Button disabled={disabled} type="submit"><Search className="h-4 w-4" />Explore</Button><Button disabled={disabled} type="button" variant="outline" size="icon" onClick={reset} aria-label="Reset graph controls"><RotateCcw className="h-4 w-4" /></Button></div>
  </form>;
}

export function MultiSelect({ label, options, value, onChange }: { label: string; options: string[]; value: string[]; onChange: (next: string[]) => void }) {
  return <label className="grid gap-1 text-xs font-medium text-muted-foreground">{label}<select multiple className="h-20 rounded-md border bg-background px-2 py-1 text-xs text-foreground" value={value} onChange={(event) => onChange([...event.currentTarget.selectedOptions].map((option) => option.value))}>{options.map((option) => <option key={option} value={option}>{humanize(option)}</option>)}</select><span className="font-normal text-muted-foreground">Select one or more</span></label>;
}

export function humanize(value: string) { return value.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").replace(/\b\w/g, (character) => character.toUpperCase()); }
