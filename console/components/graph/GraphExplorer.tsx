"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  Panel,
  ReactFlow,
  type EdgeMouseHandler,
  type NodeMouseHandler,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import { RotateCcw } from "lucide-react";
import { useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import {
  edgeToneFor,
  relationToneFor,
  statusToneFor,
} from "@/lib/graph/palette";
import type { GraphEntity, GraphRelationship, GraphSubgraph } from "@/types/graph";
import { GraphEdge, type GovernanceGraphEdge } from "./GraphEdge";
import { GraphNode, type GovernanceGraphNode } from "./GraphNode";

const nodeTypes = {
  governanceNode: GraphNode,
};

const edgeTypes = {
  governanceEdge: GraphEdge,
};

function entityLabel(entity: GraphEntity) {
  const values = [entity.immutableAttributes.name, entity.immutableAttributes.display_name, entity.immutableAttributes.model_name, entity.metadata.label, entity.metadata.name];
  return values.find((value): value is string => typeof value === "string" && Boolean(value.trim())) ?? entity.entityId;
}

function humanize(value: string) {
  return value.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

type GraphFocus =
  | { kind: "entity"; entityId: string }
  | { kind: "relationship"; relationshipId: string }
  | null;

export function GraphExplorer({
  subgraph,
  presentation = "technical",
  onSelectEntity,
  onInspectEntity,
  onSelectRelationship,
  onInspectRelationship,
}: {
  subgraph: GraphSubgraph;
  presentation?: "explore" | "technical";
  onSelectEntity: (entityId: string) => void;
  onInspectEntity: (entityId: string) => void;
  onSelectRelationship: (relationship: GraphRelationship) => void;
  onInspectRelationship: (relationship: GraphRelationship) => void;
}) {
  const initialNodes = useMemo<GovernanceGraphNode[]>(
    () => {
      const positions = layoutNodes(subgraph);
      const rootId = rootEntityId(subgraph);
      return subgraph.nodes.map((node) => ({
        id: node.entity.entityId,
        type: "governanceNode",
        position: positions.get(node.entity.entityId) ?? { x: 0, y: 0 },
        data: {
          label: presentation === "explore" ? entityLabel(node.entity) : node.entity.entityId,
          entityType: node.entity.entityType,
          lifecycle: node.entity.lifecycle,
          owner: node.entity.owner,
          depth: node.depth,
          relationTone: relationToneFor(node.entity.entityId, rootId, subgraph),
          statusTone: statusToneFor(node.entity.lifecycle),
          focusState: "default",
        },
      }));
    },
    [presentation, subgraph],
  );

  const initialEdges = useMemo<GovernanceGraphEdge[]>(
    () =>
      subgraph.edges.map((edge) => ({
        id: edge.relationship.relationshipId,
        source: edge.relationship.sourceEntityId,
        target: edge.relationship.targetEntityId,
        type: "governanceEdge",
        animated: false,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: edgeToneFor(edge.relationship, rootEntityId(subgraph)).border,
          width: 18,
          height: 18,
        },
        data: {
          label: presentation === "explore" ? humanize(edge.relationship.relationshipType) : edge.relationship.relationshipType,
          focusState: "default",
          tone: edgeToneFor(edge.relationship, rootEntityId(subgraph)),
        },
      })),
    [presentation, subgraph],
  );
  const [nodes, setNodes, onNodesChange] =
    useNodesState<GovernanceGraphNode>(initialNodes);
  const [edges, setEdges, onEdgesChange] =
    useEdgesState<GovernanceGraphEdge>(initialEdges);

  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  const relationshipById = useMemo(
    () =>
      new Map(
        subgraph.edges.map((edge) => [
          edge.relationship.relationshipId,
          edge.relationship,
        ]),
      ),
    [subgraph.edges],
  );

  const handleNodeClick: NodeMouseHandler<GovernanceGraphNode> = (_, node) => {
    applyFocus({ kind: "entity", entityId: node.id });
    onSelectEntity(node.id);
  };

  const handleEdgeClick: EdgeMouseHandler<GovernanceGraphEdge> = (_, edge) => {
    const relationship = relationshipById.get(edge.id);
    if (relationship) {
      applyFocus({ kind: "relationship", relationshipId: edge.id });
      onSelectRelationship(relationship);
    }
  };

  const handleNodeDoubleClick: NodeMouseHandler<GovernanceGraphNode> = (_, node) => {
    onInspectEntity(node.id);
  };

  const handleEdgeDoubleClick: EdgeMouseHandler<GovernanceGraphEdge> = (_, edge) => {
    const relationship = relationshipById.get(edge.id);
    if (relationship) onInspectRelationship(relationship);
  };

  function handleResetLayout() {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }

  function handleClearFocus() {
    applyFocus(null);
  }

  function applyFocus(nextFocus: GraphFocus) {
    const focusMap = focusStates(subgraph, nextFocus);
    setNodes((currentNodes) =>
      currentNodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          focusState: focusMap.nodeStates.get(node.id) ?? "default",
        },
      })),
    );
    setEdges((currentEdges) =>
      currentEdges.map((edge) => {
        if (!edge.data) {
          return edge;
        }
        const focusState = focusMap.edgeStates.get(edge.id) ?? "default";
        return {
          ...edge,
          animated: focusState === "focused" || focusState === "connected",
          data: {
            ...edge.data,
            focusState,
          },
        };
      }),
    );
  }

  if (subgraph.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        No graph data returned.
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      fitView
      fitViewOptions={{ padding: 0.16, maxZoom: 1.05 }}
      minZoom={0.2}
      maxZoom={1.8}
      nodesDraggable
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={handleNodeClick}
      onEdgeClick={handleEdgeClick}
      onNodeDoubleClick={handleNodeDoubleClick}
      onEdgeDoubleClick={handleEdgeDoubleClick}
      onPaneClick={handleClearFocus}
    >
      <Panel position="top-right">
        <Button type="button" variant="outline" size="sm" onClick={handleResetLayout}>
          <RotateCcw className="h-4 w-4" />
          Reset layout
        </Button>
      </Panel>
      <Background />
      <Controls />
      <MiniMap
        pannable
        zoomable
        maskColor="var(--graph-minimap-mask)"
        nodeStrokeWidth={2}
        className="opacity-45 transition-opacity hover:opacity-85"
        style={{
          width: 112,
          height: 82,
          background: "var(--color-card)",
          border: "1px solid var(--color-border)",
          borderRadius: 8,
          boxShadow: "0 8px 24px rgb(60 64 67 / 0.08)",
        }}
      />
    </ReactFlow>
  );
}

function focusStates(subgraph: GraphSubgraph, focus: GraphFocus) {
  const nodeStates = new Map<
    string,
    GovernanceGraphNode["data"]["focusState"]
  >();
  const edgeStates = new Map<
    string,
    NonNullable<GovernanceGraphEdge["data"]>["focusState"]
  >();

  if (focus === null) {
    return { nodeStates, edgeStates };
  }

  const activeNodeIds = new Set<string>();
  const activeEdgeIds = new Set<string>();

  if (focus.kind === "entity") {
    activeNodeIds.add(focus.entityId);
    for (const edge of subgraph.edges) {
      const relationship = edge.relationship;
      if (
        relationship.sourceEntityId === focus.entityId ||
        relationship.targetEntityId === focus.entityId
      ) {
        activeEdgeIds.add(relationship.relationshipId);
        activeNodeIds.add(relationship.sourceEntityId);
        activeNodeIds.add(relationship.targetEntityId);
      }
    }
  } else {
    const edge = subgraph.edges.find(
      (item) => item.relationship.relationshipId === focus.relationshipId,
    );
    if (edge) {
      activeEdgeIds.add(edge.relationship.relationshipId);
      activeNodeIds.add(edge.relationship.sourceEntityId);
      activeNodeIds.add(edge.relationship.targetEntityId);
    }
  }

  for (const node of subgraph.nodes) {
    if (focus.kind === "entity" && node.entity.entityId === focus.entityId) {
      nodeStates.set(node.entity.entityId, "focused");
    } else if (activeNodeIds.has(node.entity.entityId)) {
      nodeStates.set(node.entity.entityId, "connected");
    } else {
      nodeStates.set(node.entity.entityId, "dimmed");
    }
  }

  for (const edge of subgraph.edges) {
    if (
      focus.kind === "relationship" &&
      edge.relationship.relationshipId === focus.relationshipId
    ) {
      edgeStates.set(edge.relationship.relationshipId, "focused");
    } else if (activeEdgeIds.has(edge.relationship.relationshipId)) {
      edgeStates.set(edge.relationship.relationshipId, "connected");
    } else {
      edgeStates.set(edge.relationship.relationshipId, "dimmed");
    }
  }

  return { nodeStates, edgeStates };
}

function layoutNodes(subgraph: GraphSubgraph) {
  const nodesByDepth = new Map<number, typeof subgraph.nodes>();
  for (const node of subgraph.nodes) {
    const group = nodesByDepth.get(node.depth) ?? [];
    nodesByDepth.set(node.depth, [...group, node]);
  }

  const sortedDepths = [...nodesByDepth.keys()].sort((left, right) => left - right);
  const positions = new Map<string, { x: number; y: number }>();
  const sides = sidesByEntity(subgraph, sortedDepths, nodesByDepth);
  const columnSpacing = 320;
  const rowSpacing = 116;
  const nodeWidthOffset = 210;
  const nodesPerColumn = 6;

  for (const depth of sortedDepths) {
    const depthNodes = [...(nodesByDepth.get(depth) ?? [])].sort(
      (left, right) => nodeWeight(left.entity.entityType) - nodeWeight(right.entity.entityType),
    );
    const totalHeight = Math.max(0, (depthNodes.length - 1) * rowSpacing);

    const leftNodes = depthNodes.filter((node) => sides.get(node.entity.entityId) === -1);
    const rightNodes = depthNodes.filter((node) => sides.get(node.entity.entityId) === 1);

    depthNodes.forEach((node, index) => {
      const direction = depth === 0 ? 0 : (sides.get(node.entity.entityId) ?? -1);
      const lane = depth === 0 ? 0 : direction * depth;
      const sideNodes = direction < 0 ? leftNodes : rightNodes;
      const sideIndex = sideNodes.findIndex(
        (candidate) => candidate.entity.entityId === node.entity.entityId,
      );
      const sideColumn = Math.floor(sideIndex / nodesPerColumn);
      const sideRow = sideIndex % nodesPerColumn;
      const rowsInColumn = Math.min(nodesPerColumn, sideNodes.length);
      const sideHeight = Math.max(0, (rowsInColumn - 1) * rowSpacing);
      positions.set(node.entity.entityId, {
        x: depth === 0
          ? -nodeWidthOffset
          : direction * (Math.abs(lane) * columnSpacing + sideColumn * 220) - nodeWidthOffset,
        y: depth === 0
          ? index * rowSpacing - totalHeight / 2
          : sideRow * rowSpacing - sideHeight / 2,
      });
    });
  }

  return positions;
}

function sidesByEntity(
  subgraph: GraphSubgraph,
  sortedDepths: number[],
  nodesByDepth: Map<number, typeof subgraph.nodes>,
) {
  const rootId = rootEntityId(subgraph);
  const sides = new Map<string, -1 | 1>();
  const nodeDepths = new Map<string, number>();
  subgraph.nodes.forEach((node) => nodeDepths.set(node.entity.entityId, node.depth));

  for (const depth of sortedDepths) {
    if (depth === 0) continue;
    for (const node of nodesByDepth.get(depth) ?? []) {
      const entityId = node.entity.entityId;
      const directRelationship = subgraph.edges.find(
        (edge) =>
          (edge.relationship.sourceEntityId === rootId && edge.relationship.targetEntityId === entityId)
          || (edge.relationship.targetEntityId === rootId && edge.relationship.sourceEntityId === entityId),
      )?.relationship;
      if (directRelationship) {
        sides.set(
          entityId,
          directRelationship.sourceEntityId === rootId ? 1 : -1,
        );
        continue;
      }
      const parentRelationship = subgraph.edges.find((edge) => {
        const relationship = edge.relationship;
        const adjacentId = relationship.sourceEntityId === entityId
          ? relationship.targetEntityId
          : relationship.targetEntityId === entityId
            ? relationship.sourceEntityId
            : null;
        return adjacentId !== null && nodeDepths.get(adjacentId) === depth - 1;
      })?.relationship;
      const parentId = parentRelationship?.sourceEntityId === entityId
        ? parentRelationship.targetEntityId
        : parentRelationship?.targetEntityId;
      sides.set(entityId, parentId ? (sides.get(parentId) ?? -1) : -1);
    }
  }
  return sides;
}

function rootEntityId(subgraph: GraphSubgraph) {
  return (
    subgraph.nodes.find((node) => node.depth === 0)?.entity.entityId ??
    subgraph.nodes[0]?.entity.entityId ??
    ""
  );
}

function nodeWeight(entityType: string) {
  const order = [
    "GovernanceDecision",
    "Experiment",
    "EvaluationRun",
    "EvaluationResult",
    "Metric",
    "Candidate",
    "PromptVersion",
    "ModelVersion",
    "DatasetVersion",
    "EvaluationProvider",
    "Actor",
    "Policy",
  ];
  const index = order.indexOf(entityType);
  return index === -1 ? order.length : index;
}
