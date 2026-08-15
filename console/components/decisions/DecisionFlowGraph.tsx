"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  MiniMap,
  Panel,
  Position,
  ReactFlow,
  getBezierPath,
  useEdgesState,
  useNodesState,
  type EdgeProps,
  type NodeProps,
} from "@xyflow/react";
import * as Dialog from "@radix-ui/react-dialog";
import { Maximize2, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  DecisionFlowEdge,
  DecisionFlowNode,
} from "@/lib/decisions/flow";

const nodeTypes = {
  decisionNode: DecisionNode,
};

const edgeTypes = {
  decisionEdge: DecisionEdge,
};

export function DecisionFlowGraph({
  nodes,
  edges,
  title,
}: {
  nodes: DecisionFlowNode[];
  edges: DecisionFlowEdge[];
  title?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const initialEdges = useMemo(
    () =>
      edges.map((edge) => ({
        ...edge,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 16,
          height: 16,
          color: "#5f6368",
        },
      })),
    [edges],
  );

  const [flowNodes, setNodes, onNodesChange] =
    useNodesState<DecisionFlowNode>(nodes);
  const [flowEdges, setEdges, onEdgesChange] =
    useEdgesState<DecisionFlowEdge>(initialEdges);

  useEffect(() => {
    setNodes(nodes);
  }, [nodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  function handleResetLayout() {
    setNodes(nodes);
    setEdges(initialEdges);
  }

  const graph = (isExpanded: boolean) => (
    <ReactFlow
      nodes={flowNodes}
      edges={flowEdges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      fitView
      fitViewOptions={{ padding: isExpanded ? 0.1 : 0.18, maxZoom: 1 }}
      minZoom={0.25}
      maxZoom={1.6}
      nodesDraggable
      nodesConnectable={false}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
    >
      <Panel position="top-right">
        <div className="flex items-center gap-2">
          {title && !isExpanded ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setExpanded(true)}
              aria-label={`Expand ${title}`}
            >
              <Maximize2 className="h-4 w-4" />
              Expand
            </Button>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleResetLayout}
          >
            <RotateCcw className="h-4 w-4" />
            Reset
          </Button>
        </div>
      </Panel>
      <Background gap={18} size={1} />
      <Controls />
      <MiniMap
        pannable
        zoomable
        maskColor="rgb(248 250 252 / 0.55)"
        nodeStrokeWidth={2}
        className="opacity-45 transition-opacity hover:opacity-85"
        style={{
          width: isExpanded ? 150 : 110,
          height: isExpanded ? 106 : 78,
          background: "rgb(255 255 255 / 0.76)",
          border: "1px solid hsl(220 13% 88%)",
          borderRadius: 8,
          boxShadow: "0 8px 24px rgb(60 64 67 / 0.08)",
        }}
      />
    </ReactFlow>
  );

  return (
    <>
      {graph(false)}
      {title ? (
        <Dialog.Root open={expanded} onOpenChange={setExpanded}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm" />
            <Dialog.Content className="fixed inset-4 z-50 flex max-h-[calc(100dvh-2rem)] flex-col overflow-hidden rounded-lg border bg-background p-4 shadow-2xl focus:outline-none">
              <div className="flex items-start justify-between gap-4 border-b pb-3">
                <div>
                  <Dialog.Title className="text-base font-semibold">
                    {title}
                  </Dialog.Title>
                  <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                    Explore the full relationship graph. Select an edge to reveal its relationship label.
                  </Dialog.Description>
                </div>
                <Dialog.Close asChild>
                  <Button type="button" variant="ghost" size="icon" aria-label="Close expanded graph">
                    <X className="h-4 w-4" />
                  </Button>
                </Dialog.Close>
              </div>
              <div className="min-h-0 flex-1 pt-4">
                {graph(true)}
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      ) : null}
    </>
  );
}

function DecisionNode({ data, selected }: NodeProps<DecisionFlowNode>) {
  const tone = toneFor(data.tone);
  return (
    <div
      className="relative h-[92px] w-52 overflow-hidden rounded-lg border bg-card px-3 py-2 shadow-sm transition-all"
      style={{
        background: tone.background,
        borderColor: selected ? tone.selected : tone.border,
        boxShadow: selected
          ? `0 14px 30px ${tone.shadow}`
          : "0 3px 10px rgb(60 64 67 / 0.08)",
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="h-2 w-2 border-primary bg-background opacity-0"
      />
      <Handle
        type="target"
        position={Position.Top}
        className="h-2 w-2 border-primary bg-background opacity-0"
      />
      <div
        className="absolute inset-y-0 left-0 w-0.5"
        style={{ background: tone.border }}
      />
      <div className="flex items-center justify-between gap-2">
        <Badge
          variant="outline"
          className="max-w-[142px] truncate border px-2 py-0 text-[10px]"
          style={{
            background: tone.badgeBackground,
            borderColor: tone.border,
            color: tone.text,
          }}
        >
          {data.entityType}
        </Badge>
        <span className="text-[11px] text-muted-foreground">
          d{data.depth}
        </span>
      </div>
      <div className="mt-2 truncate text-[13px] font-semibold text-foreground">
        {data.label}
      </div>
      <div className="mt-1 truncate text-[11px] text-muted-foreground">
        {data.subtitle}
      </div>
      <div className="mt-2 flex items-center gap-1 text-[11px] font-medium">
        <span
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ background: tone.border }}
        />
        <span className="truncate" style={{ color: tone.text }}>
          {data.status}
        </span>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="h-2 w-2 border-primary bg-background opacity-0"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="h-2 w-2 border-primary bg-background opacity-0"
      />
    </div>
  );
}

function DecisionEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  selected,
  data,
}: EdgeProps<DecisionFlowEdge>) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: selected ? "#0f766e" : "#6b7280",
          strokeOpacity: selected ? 0.9 : 0.5,
          strokeWidth: selected ? 2.2 : 1.2,
        }}
      />
      {selected ? (
        <EdgeLabelRenderer>
          <div
            className="pointer-events-none absolute max-w-32 truncate rounded-md border bg-white/90 px-1.5 py-px text-[8px] font-medium text-slate-700 shadow-sm"
            style={{
              borderColor: "#0f766e",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
          >
            {data?.label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

function toneFor(tone: "root" | "evidence" | "lineage" | "muted") {
  if (tone === "root") {
    return {
      background: "#f7f8fb",
      badgeBackground: "#eceef8",
      border: "#7d89b0",
      selected: "#596582",
      shadow: "rgb(89 101 130 / 0.22)",
      text: "#424b63",
    };
  }
  if (tone === "evidence") {
    return {
      background: "#f8fcfc",
      badgeBackground: "#eff8f7",
      border: "#65c9c2",
      selected: "#239b95",
      shadow: "rgb(101 201 194 / 0.22)",
      text: "#23706d",
    };
  }
  if (tone === "lineage") {
    return {
      background: "#fffdf8",
      badgeBackground: "#f7f0db",
      border: "#c4a35a",
      selected: "#8a6a22",
      shadow: "rgb(196 163 90 / 0.2)",
      text: "#6f551a",
    };
  }
  return {
    background: "#ffffff",
    badgeBackground: "#eef2f7",
    border: "#9aa0a6",
    selected: "#5f6368",
    shadow: "rgb(95 99 104 / 0.22)",
    text: "#3c4043",
  };
}
