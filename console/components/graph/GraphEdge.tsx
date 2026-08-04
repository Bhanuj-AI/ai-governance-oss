"use client";

import {
  BaseEdge,
  EdgeLabelRenderer,
  type Edge,
  type EdgeProps,
  getBezierPath,
} from "@xyflow/react";

export type GovernanceGraphEdgeData = {
  label: string;
  focusState: "default" | "focused" | "connected" | "dimmed";
  tone: {
    background: string;
    border: string;
    selected: string;
    focused: string;
    shadow: string;
    text: string;
    labelText: string;
  };
};

export type GovernanceGraphEdge = Edge<
  GovernanceGraphEdgeData,
  "governanceEdge"
>;

export function GraphEdge({
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
}: EdgeProps<GovernanceGraphEdge>) {
  const focusState = data?.focusState ?? "default";
  const isEmphasized =
    selected || focusState === "focused" || focusState === "connected";
  const isDimmed = focusState === "dimmed";
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
          stroke: isEmphasized ? data?.tone.focused : data?.tone.border,
          strokeOpacity: isDimmed ? 0.28 : isEmphasized ? 1 : 0.5,
          strokeWidth: isEmphasized ? 2.8 : 1.1,
        }}
      />
      <EdgeLabelRenderer>
        <div
          className="graph-edge-label pointer-events-none absolute rounded-md border bg-card px-2 py-0.5 text-[9px] font-semibold tracking-wide shadow-sm"
          style={{
            borderColor: data?.tone.border,
            color: data?.tone.labelText,
            opacity: isDimmed ? 0.62 : 0.96,
            boxShadow: data ? `0 2px 6px ${data.tone.shadow}` : undefined,
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          }}
        >
          {data?.label}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
