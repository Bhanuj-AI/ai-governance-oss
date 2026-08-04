import { MarkerType, type Edge, type Node } from "@xyflow/react";
import type { Replay, ReplayResult } from "@/types/replay";

export type ReplayLineageNodeData = {
  label: string;
  entityType: string;
  reference: string;
  href?: string;
};

export type ReplayLineageGraph = {
  nodes: Node<ReplayLineageNodeData>[];
  edges: Edge[];
};

/** Maps persisted Replay references to a deterministic, read-only React Flow graph. */
export class ReplayLineageGraphMapper {
  static map(replay: Replay, result?: ReplayResult | null): ReplayLineageGraph {
    const nodes: Node<ReplayLineageNodeData>[] = [];
    const edges: Edge[] = [];
    const add = (id: string | null, entityType: string, label: string, column: number, row = 0, href?: string) => {
      if (!id) return;
      nodes.push({ id, type: "default", position: { x: column * 260, y: row * 150 }, data: { label, entityType, reference: id, href } });
    };
    const link = (source: string | null, target: string | null, label: string) => {
      if (!source || !target) return;
      edges.push({ id: `${source}:${label}:${target}`, source, target, label, markerEnd: { type: MarkerType.ArrowClosed }, style: { strokeWidth: 1.5 } });
    };

    add(replay.source_execution_id, "WorkflowExecution", "Source execution", 0, 0);
    add(replay.replay_id, "Replay", `Replay ${shortId(replay.replay_id)}`, 1, 0);
    add(replay.job_id, "Job", "Execution job", 2, -1, `/jobs?job_id=${encodeURIComponent(replay.job_id ?? "")}`);
    add(replay.replay_execution_id, "WorkflowExecution", "Replay execution", 2, 0);
    add(replay.evaluation_job_id, "Job", "Evaluation job", 3, -1, `/jobs?job_id=${encodeURIComponent(replay.evaluation_job_id ?? "")}`);
    add(replay.baseline_evaluation_id, "EvaluationResult", "Baseline evaluation", 3, 0);
    add(replay.replay_evaluation_id, "EvaluationResult", "Replay evaluation", 3, 1);
    add(replay.comparison_id, "EvaluationComparison", "Comparison", 4, 0);
    add(replay.drift_id, "DriftAnalysis", "Drift analysis", 5, 0);
    add(result?.result_id ?? replay.result_id, "ReplayResult", "Replay result", 6, 0);

    link(replay.replay_id, replay.source_execution_id, "REPLAY_OF");
    link(replay.replay_id, replay.job_id, "SUBMITTED_AS");
    link(replay.replay_id, replay.replay_execution_id, "PRODUCED");
    link(replay.replay_id, replay.evaluation_job_id, "SUBMITTED_AS");
    link(replay.replay_id, replay.baseline_evaluation_id, "GENERATED_FROM");
    link(replay.replay_id, replay.replay_evaluation_id, "PRODUCED");
    link(replay.replay_id, replay.comparison_id, "PRODUCED");
    link(replay.replay_id, replay.drift_id, "CAUSED_DRIFT");
    link(replay.replay_id, result?.result_id ?? replay.result_id, "RESULTED_IN");
    return { nodes, edges };
  }
}

function shortId(value: string) { return value.length > 14 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value; }
