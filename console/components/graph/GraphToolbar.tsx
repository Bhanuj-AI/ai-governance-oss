"use client";

import { RotateCcw, Search } from "lucide-react";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { RelationshipDirection } from "@/types/graph";

export type GraphLoadRequest = {
  entityType: string;
  entityId: string;
  depth: number;
  direction: RelationshipDirection;
  relationshipTypes: string[];
  entityTypes: string[];
  awaitProjection?: boolean;
};

const MAX_DEPTH = 5;
const ENTITY_TYPES = [
  "Candidate",
  "Dataset",
  "DatasetVersion",
  "DriftAnalysis",
  "EvaluationComparison",
  "EvaluationHistory",
  "EvaluationProvider",
  "EvaluationResult",
  "EvaluationRun",
  "Experiment",
  "GovernanceDecision",
  "GovernanceInsight",
  "GovernanceReport",
  "Job",
  "Leaderboard",
  "MCPAuditRecord",
  "Metric",
  "Model",
  "ModelVersion",
  "Policy",
  "Prompt",
  "PromptVersion",
  "ReplayInvestigation",
  "WorkflowExecution",
];

export function GraphToolbar({
  disabled,
  request,
  onLoad,
  onReset,
}: {
  disabled?: boolean;
  request: GraphLoadRequest | null;
  onLoad: (request: GraphLoadRequest) => void;
  onReset: () => void;
}) {
  const [entityType, setEntityType] = useState(request?.entityType ?? "Candidate");
  const [entityId, setEntityId] = useState(request?.entityId ?? "");
  const [depth, setDepth] = useState(request?.depth ?? 1);
  const [direction, setDirection] = useState<RelationshipDirection>(request?.direction ?? "both");
  const [relationshipType, setRelationshipType] = useState(request?.relationshipTypes.join(", ") ?? "");
  const [entityTypeFilter, setEntityTypeFilter] = useState(request?.entityTypes.join(", ") ?? "");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onLoad({
      entityType: entityType.trim(),
      entityId: entityId.trim(),
      depth: Math.min(Math.max(depth, 1), MAX_DEPTH),
      direction,
      relationshipTypes: splitFilter(relationshipType),
      entityTypes: splitFilter(entityTypeFilter),
    });
  }

  function handleReset() {
    setEntityType("Candidate");
    setEntityId("");
    setDepth(1);
    setDirection("both");
    setRelationshipType("");
    setEntityTypeFilter("");
    onReset();
  }

  return (
    <div className="overflow-x-auto border-b bg-card">
      <form
        className="grid min-w-[1240px] grid-cols-[220px_minmax(260px,1fr)_110px_150px_minmax(210px,1fr)_minmax(210px,1fr)_auto_auto] items-end gap-4 p-4"
        onSubmit={handleSubmit}
      >
        <label className="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
          Entity Type
          <select
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={entityType}
            onChange={(event) => setEntityType(event.target.value)}
            required
          >
            {ENTITY_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        <label className="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
          Entity ID
          <Input
            value={entityId}
            onChange={(event) => setEntityId(event.target.value)}
            placeholder={
              entityType === "Leaderboard"
                ? "leaderboard, experiment, or candidate ID"
                : "candidate-1"
            }
            required
          />
        </label>
        <label className="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
          Depth
          <Input
            type="number"
            min={1}
            max={MAX_DEPTH}
            value={depth}
            onChange={(event) => setDepth(Number(event.target.value))}
          />
        </label>
        <label className="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
          Direction
          <select
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={direction}
            onChange={(event) =>
              setDirection(event.target.value as RelationshipDirection)
            }
          >
            <option value="both">Both</option>
            <option value="incoming">Incoming</option>
            <option value="outgoing">Outgoing</option>
          </select>
        </label>
        <label className="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
          Relationship Type
          <Input
            value={relationshipType}
            onChange={(event) => setRelationshipType(event.target.value)}
            placeholder="comma separated"
          />
        </label>
        <label className="grid min-w-0 gap-1 text-xs font-medium text-muted-foreground">
          Node Type Filter
          <Input
            value={entityTypeFilter}
            onChange={(event) => setEntityTypeFilter(event.target.value)}
            placeholder="comma separated"
          />
        </label>
        <Button disabled={disabled} type="submit">
          <Search className="h-4 w-4" />
          Load
        </Button>
        <Button
          disabled={disabled}
          type="button"
          variant="outline"
          onClick={handleReset}
        >
          <RotateCcw className="h-4 w-4" />
          Reset
        </Button>
      </form>
    </div>
  );
}

function splitFilter(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
