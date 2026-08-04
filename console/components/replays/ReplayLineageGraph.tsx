"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  MarkerType,
  Panel,
  ReactFlow,
  type ReactFlowInstance,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import { ExternalLink, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { ReplayLineageGraphMapper } from "@/lib/replays/ReplayLineageGraphMapper";
import type { Replay, ReplayResult } from "@/types/replay";
import { ReplayStatusBadge } from "./ReplayStatusBadge";

const fitViewOptions = { padding: 0.18 };

export function ReplayLineageGraph({
  replay,
  result,
}: {
  replay: Replay;
  result?: ReplayResult | null;
}) {
  const graph = useMemo(
    () => ReplayLineageGraphMapper.map(replay, result),
    [replay, result],
  );
  const initialEdges = useMemo(
    () =>
      graph.edges.map((edge) => ({
        ...edge,
        markerEnd: { type: MarkerType.ArrowClosed },
        labelStyle: { fontSize: 10 },
        labelBgPadding: [5, 3] as [number, number],
        labelBgBorderRadius: 4,
      })),
    [graph.edges],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(graph.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNode, setSelectedNode] = useState<
    (typeof graph.nodes)[number] | null
  >(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const flowInstance = useRef<
    ReactFlowInstance<(typeof graph.nodes)[number], (typeof initialEdges)[number]> | null
  >(null);

  useEffect(() => {
    setNodes(graph.nodes);
  }, [graph.nodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  useEffect(() => {
    function dismissWhenOutside(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setSelectedNode(null);
      }
    }
    document.addEventListener("pointerdown", dismissWhenOutside);
    return () => document.removeEventListener("pointerdown", dismissWhenOutside);
  }, []);

  function handleResetLayout() {
    setNodes(graph.nodes);
    setEdges(initialEdges);
    setSelectedNode(null);
    requestAnimationFrame(() => {
      flowInstance.current?.fitView(fitViewOptions);
    });
  }

  return (
    <div ref={containerRef} className="h-[460px] rounded-md border bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={fitViewOptions}
        minZoom={0.3}
        maxZoom={1.5}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        panOnDrag
        onInit={(instance) => {
          flowInstance.current = instance;
        }}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => setSelectedNode(node)}
        onEdgeClick={() => setSelectedNode(null)}
        onPaneClick={() => setSelectedNode(null)}
      >
        <Panel position="top-right">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleResetLayout}
          >
            <RotateCcw className="h-4 w-4" />
            Reset
          </Button>
        </Panel>
        {selectedNode ? (
          <Panel position="top-left">
            <NodeInspector
              node={selectedNode}
              replay={replay}
              result={result}
              onClose={() => setSelectedNode(null)}
            />
          </Panel>
        ) : null}
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

function NodeInspector({
  node,
  replay,
  result,
  onClose,
}: {
  node: ReturnType<typeof ReplayLineageGraphMapper.map>["nodes"][number];
  replay: Replay;
  result?: ReplayResult | null;
  onClose: () => void;
}) {
  const details = nodeDetails(node, replay, result);
  return (
    <aside className="w-[min(340px,calc(100vw-5rem))] rounded-md border bg-card p-3 shadow-lg">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {node.data.entityType}
          </div>
          <div className="mt-1 font-medium">{node.data.label}</div>
        </div>
        <button
          type="button"
          className="rounded-sm p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="Close node details"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-3 rounded bg-muted p-2 font-mono text-xs break-all">
        {node.data.reference}
        <CopyButton
          value={node.data.reference}
          variant="ghost"
          size="sm"
          className="ml-2 h-auto w-auto align-middle p-0 text-muted-foreground hover:text-foreground"
          copyTitle="Copy reference"
          iconClassName="h-3.5 w-3.5"
        />
      </div>
      <dl className="mt-3 space-y-2 text-sm">
        {details.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[110px_1fr] gap-2">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="break-all">
              {label === "Status" ? <ReplayStatusBadge status={replay.status} /> : value}
            </dd>
          </div>
        ))}
      </dl>
      {node.data.entityType === "Replay" && Object.keys(replay.metadata).length ? (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer font-medium">Replay metadata</summary>
          <pre className="mt-2 max-h-32 overflow-auto rounded bg-muted p-2 text-xs">
            {JSON.stringify(replay.metadata, null, 2)}
          </pre>
        </details>
      ) : null}
      {node.data.href ? (
        <a
          className="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline"
          href={node.data.href}
        >
          Open related record
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      ) : null}
    </aside>
  );
}

function nodeDetails(
  node: ReturnType<typeof ReplayLineageGraphMapper.map>["nodes"][number],
  replay: Replay,
  result?: ReplayResult | null,
): Array<[string, string]> {
  const details: Array<[string, string | null | undefined]> = [
    ["Entity type", node.data.entityType],
  ];
  if (node.id === replay.replay_id) {
    details.push(
      ["Status", replay.status],
      ["Mode", replay.mode],
      ["Requested by", replay.requested_by],
      ["Created", new Date(replay.created_at).toLocaleString()],
      ["Configuration hash", replay.configuration?.configuration_hash],
    );
  } else if (node.id === replay.source_execution_id) {
    details.push(
      ["Role", "Historical source"],
      ["Workflow", replay.configuration?.workflow_id],
      ["Workflow version", replay.configuration?.workflow_version],
      ["Input snapshot", replay.configuration?.input_snapshot_ref],
      ["State snapshot", replay.configuration?.state_snapshot_ref],
    );
  } else if (node.id === replay.replay_execution_id) {
    details.push(
      ["Role", "Replay-produced execution"],
      ["Attempt", String(replay.attempt_count)],
      ["Execution completed", formatDate(replay.execution_completed_at)],
    );
  } else if (node.id === replay.job_id) {
    details.push(
      ["Role", "Replay execution job"],
      ["Queued", formatDate(replay.queued_at)],
      ["Started", formatDate(replay.started_at)],
    );
  } else if (node.id === replay.evaluation_job_id) {
    details.push(
      ["Role", "Replay evaluation job"],
      ["Started", formatDate(replay.evaluation_started_at)],
      ["Completed", formatDate(replay.evaluation_completed_at)],
    );
  } else if (node.id === replay.comparison_id) {
    details.push(
      ["Role", "Evaluation comparison"],
      ["Completed", formatDate(replay.comparison_completed_at)],
      ["Score delta", formatScoreDelta(result?.comparison_summary.overall_score_delta)],
    );
  } else if (node.id === replay.drift_id) {
    details.push(
      ["Role", "Drift analysis"],
      ["Severity", result?.drift_summary.severity],
      ["Changed metrics", result?.drift_summary.changed_metrics.join(", ")],
    );
  } else if (node.id === (result?.result_id ?? replay.result_id)) {
    details.push(
      ["Role", "Immutable replay result"],
      ["Baseline strategy", result?.baseline_strategy],
      ["Created", formatDate(result?.created_at)],
    );
  } else if (node.id === replay.baseline_evaluation_id) {
    details.push(["Role", "Baseline evaluation evidence"]);
  } else if (node.id === replay.replay_evaluation_id) {
    details.push(["Role", "Replay evaluation evidence"]);
  }
  return details.filter(
    (detail): detail is [string, string] => Boolean(detail[1]),
  );
}

function formatDate(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : null;
}

function formatScoreDelta(value: number | null | undefined) {
  return value === null || value === undefined ? null : value.toFixed(3);
}
