"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import {
  getDownstream,
  getNeighbourhood,
  getUpstream,
} from "@/lib/api/graph";
import { AIGovernanceApiError } from "@/lib/api/client";
import type { GraphRelationship, GraphSubgraph } from "@/types/graph";
import { GraphExplorer } from "./GraphExplorer";
import {
  GraphToolbar,
  type GraphLoadRequest,
} from "./GraphToolbar";
import { EntityDetailPanel } from "./EntityDetailPanel";

type Selection =
  | { kind: "entity"; entityId: string }
  | { kind: "relationship"; relationship: GraphRelationship }
  | null;

class LeaderboardProjectionPendingError extends Error {}

export function GraphWorkspace() {
  const searchParams = useSearchParams();
  const [request, setRequest] = useState<GraphLoadRequest | null>(() =>
    requestFromSearchParams(searchParams),
  );
  const [selection, setSelection] = useState<Selection>(null);

  const query = useQuery({
    queryKey: ["ontology-graph", request],
    queryFn: () => loadGraph(request),
    enabled: request !== null,
    retry: (failureCount, error) =>
      error instanceof LeaderboardProjectionPendingError && failureCount < 15,
    retryDelay: 2000,
  });

  const subgraph = query.data ?? emptySubgraph;

  const selectedEntity = useMemo(
    () =>
      selection?.kind === "entity"
        ? subgraph.nodes.find((node) => node.entity.entityId === selection.entityId)
            ?.entity
        : undefined,
    [selection, subgraph.nodes],
  );

  const selectedRelationship =
    selection?.kind === "relationship" ? selection.relationship : undefined;

  function handleLoad(nextRequest: GraphLoadRequest) {
    setSelection(null);
    setRequest(nextRequest);
  }

  function handleReset() {
    setSelection(null);
    setRequest(null);
  }

  return (
    <div className="grid h-[calc(100vh-3.5rem)] grid-rows-[auto_1fr]">
      <GraphToolbar
        key={request ? graphRequestKey(request) : "empty"}
        disabled={query.isFetching}
        request={request}
        onLoad={handleLoad}
        onReset={handleReset}
      />
      <div className="grid min-h-0 grid-cols-[1fr_360px]">
        <section className="relative min-w-0">
          {query.isError ? <GraphError error={query.error} /> : null}
          {query.isFetching ? (
            <div className="absolute left-4 top-4 z-10 rounded-md border bg-card px-3 py-2 text-sm shadow-sm">
              {request?.awaitProjection
                ? "Waiting for the leaderboard ontology projection…"
                : "Loading graph data..."}
            </div>
          ) : null}
          {!request ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Enter an ontology entity to load its graph neighbourhood.
            </div>
          ) : (
            <GraphExplorer
              subgraph={subgraph}
              onSelectEntity={(entityId) =>
                setSelection({ kind: "entity", entityId })
              }
              onSelectRelationship={(relationship) =>
                setSelection({ kind: "relationship", relationship })
              }
            />
          )}
        </section>
        <EntityDetailPanel
          entity={selectedEntity}
          relationship={selectedRelationship}
        />
      </div>
    </div>
  );
}

async function loadGraph(request: GraphLoadRequest | null) {
  if (!request) {
    return emptySubgraph;
  }

  if (request.entityType === "Leaderboard") {
    return loadLeaderboardGraph(request);
  }

  const shared = {
    entityType: request.entityType,
    entityId: request.entityId,
    depth: request.depth,
    relationshipTypes: request.relationshipTypes,
    limit: 100,
  };

  if (request.direction === "incoming") {
    return getUpstream(shared);
  }

  if (request.direction === "outgoing") {
    return getDownstream(shared);
  }

  return getNeighbourhood({
    ...shared,
    entityTypes: request.entityTypes,
  });
}

async function loadLeaderboardGraph(request: GraphLoadRequest) {
  try {
    const direct = await getNeighbourhood({
      entityType: "Leaderboard",
      entityId: request.entityId,
      depth: request.depth,
      relationshipTypes: request.relationshipTypes,
      entityTypes: request.entityTypes,
      limit: 100,
    });
    if (
      direct.nodes.some((node) => node.entity.entityType === "Leaderboard")
    ) {
      return direct;
    }
  } catch (error) {
    if (!(error instanceof AIGovernanceApiError) || error.status !== 404) {
      throw error;
    }
  }

  for (const entityType of ["Experiment", "Candidate"]) {
    try {
      const context = await getDownstream({
        entityType,
        entityId: request.entityId,
        depth: 3,
        relationshipTypes: [],
        limit: 100,
      });
      const leaderboard = context.nodes.find(
        (node) => node.entity.entityType === "Leaderboard",
      );
      if (leaderboard) {
        return getNeighbourhood({
          entityType: "Leaderboard",
          entityId: leaderboard.entity.entityId,
          depth: request.depth,
          relationshipTypes: request.relationshipTypes,
          entityTypes: request.entityTypes,
          limit: 100,
        });
      }
    } catch (error) {
      if (!(error instanceof AIGovernanceApiError) || error.status !== 404) {
        throw error;
      }
    }
  }

  if (request.awaitProjection) {
    throw new LeaderboardProjectionPendingError(
      "The leaderboard was saved and its ontology projection is pending.",
    );
  }
  throw new Error(`No leaderboard was found for experiment or candidate '${request.entityId}'.`);
}

function GraphError({ error }: { error: Error }) {
  const message =
    error instanceof AIGovernanceApiError
      ? `${error.code}: ${error.message}`
      : error.message;

  return (
    <div className="absolute left-4 right-4 top-4 z-10 flex items-start gap-2 rounded-md border border-destructive/30 bg-card px-3 py-2 text-sm text-destructive shadow-sm">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

const emptySubgraph: GraphSubgraph = {
  nodes: [],
  edges: [],
};

function requestFromSearchParams(
  searchParams: ReturnType<typeof useSearchParams>,
): GraphLoadRequest | null {
  const entityType = searchParams.get("entityType")?.trim();
  const entityId = searchParams.get("entityId")?.trim();
  if (!entityType || !entityId) {
    return null;
  }
  const requestedDepth = Number(searchParams.get("depth") ?? "1");
  return {
    entityType,
    entityId,
    depth: Math.min(Math.max(Number.isFinite(requestedDepth) ? requestedDepth : 1, 1), 5),
    direction: "both",
    relationshipTypes: [],
    entityTypes: [],
    awaitProjection: searchParams.get("awaitProjection") === "true",
  };
}

function graphRequestKey(request: GraphLoadRequest) {
  return [
    request.entityType,
    request.entityId,
    request.depth,
    request.direction,
    request.relationshipTypes.join(","),
    request.entityTypes.join(","),
    String(request.awaitProjection),
  ].join("|");
}
