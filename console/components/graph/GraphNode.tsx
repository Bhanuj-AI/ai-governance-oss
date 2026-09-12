"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Badge } from "@/components/ui/badge";
import type { GraphTone } from "@/lib/graph/palette";

export type GovernanceGraphNodeData = {
  label: string;
  entityType: string;
  lifecycle: string;
  owner: string;
  depth: number;
  relationTone: GraphTone;
  statusTone: GraphTone;
  focusState: "default" | "focused" | "connected" | "dimmed";
};

export type GovernanceGraphNode = Node<
  GovernanceGraphNodeData,
  "governanceNode"
>;

export function GraphNode({ data, selected }: NodeProps<GovernanceGraphNode>) {
  const isEmphasized =
    selected || data.focusState === "focused" || data.focusState === "connected";

  return (
    <div
      className="graph-governance-node relative w-44 overflow-hidden rounded-lg border bg-card px-3 py-2 transition-all duration-150"
      style={{
        borderColor: isEmphasized
          ? data.relationTone.selected
          : data.relationTone.border,
        boxShadow: isEmphasized
          ? `0 14px 30px ${data.relationTone.shadow}`
          : "0 3px 10px rgb(60 64 67 / 0.08)",
        // Keep labels readable while focus styling is carried by the border,
        // shadow, and connected edges rather than fading the entire node.
        opacity: 1,
        transform: selected || data.focusState === "focused" ? "translateY(-2px)" : "translateY(0)",
      }}
    >
      <div
        className="absolute inset-y-0 left-0 w-0.5"
        style={{ background: data.relationTone.border }}
      />
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
      <div className="flex items-center justify-between gap-3">
        <Badge
          variant="outline"
          className="graph-governance-node-badge ml-1 max-w-[122px] truncate border px-2 py-0 text-[10px] font-medium"
          style={{
            background: data.relationTone.badgeBackground,
            borderColor: data.relationTone.border,
            color: data.relationTone.text,
          }}
        >
          {data.entityType}
        </Badge>
        <span className="text-[11px] text-muted-foreground">d{data.depth}</span>
      </div>
      <div className="mt-2 truncate text-[13px] font-semibold text-foreground">
        {data.label}
      </div>
      <div className="mt-1 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span className="truncate">{data.owner}</span>
        <span
          className="inline-flex shrink-0 items-center gap-1 font-medium"
          style={{
            color: data.statusTone.text,
          }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: data.statusTone.border }}
          />
          {data.lifecycle}
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
