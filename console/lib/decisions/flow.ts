import type { Edge, Node } from "@xyflow/react";
import type {
  DecisionEvidenceGraph,
  DecisionLineage,
  EvidenceNode,
} from "@/types/decision";

export type DecisionFlowNodeData = {
  label: string;
  entityType: string;
  subtitle: string;
  status: string;
  depth: number;
  tone: "root" | "evidence" | "lineage" | "muted";
};

export type DecisionFlowNode = Node<DecisionFlowNodeData, "decisionNode">;

export type DecisionFlowEdgeData = {
  label: string;
};

export type DecisionFlowEdge = Edge<DecisionFlowEdgeData, "decisionEdge">;

export function evidenceGraphToFlow(
  graph: DecisionEvidenceGraph,
): { nodes: DecisionFlowNode[]; edges: DecisionFlowEdge[] } {
  const rootId = nodeKey(graph.targetType, graph.targetId);
  const depths = evidenceDepths(graph, rootId);
  const positions = layoutByDepth(
    graph.nodes.map((node) => ({
      id: nodeKey(node.entityType, node.entityId),
      depth: depths.get(nodeKey(node.entityType, node.entityId)) ?? 1,
      weight: nodeWeight(node.entityType),
    })),
  );

  return {
    nodes: graph.nodes.map((node) => {
      const id = nodeKey(node.entityType, node.entityId);
      return {
        id,
        type: "decisionNode",
        position: positions.get(id) ?? { x: 0, y: 0 },
        data: {
          label: node.label ?? node.entityId,
          entityType: node.entityType,
          subtitle: node.entityId,
          status: node.lifecycle ?? "evidence",
          depth: depths.get(id) ?? 1,
          tone: id === rootId ? "root" : "evidence",
        },
      };
    }),
    edges: graph.edges.map((edge, index) => ({
      id: [
        nodeKey(edge.sourceType, edge.sourceId),
        edge.relationshipType,
        nodeKey(edge.targetType, edge.targetId),
        index,
      ].join(":"),
      source: nodeKey(edge.sourceType, edge.sourceId),
      target: nodeKey(edge.targetType, edge.targetId),
      type: "decisionEdge",
      data: { label: edge.relationshipType },
    })),
  };
}

export function lineageToFlow(
  lineage: DecisionLineage,
): { nodes: DecisionFlowNode[]; edges: DecisionFlowEdge[] } {
  const rootId = nodeKey("GovernanceDecision", lineage.decision.decisionId);
  const positions = layoutByDepth(
    lineage.subgraph.nodes.map((node) => ({
      id: nodeKey(node.entity.entityType, node.entity.entityId),
      depth: node.depth,
      weight: nodeWeight(node.entity.entityType),
    })),
  );

  return {
    nodes: lineage.subgraph.nodes.map((node) => {
      const id = nodeKey(node.entity.entityType, node.entity.entityId);
      return {
        id,
        type: "decisionNode",
        position: positions.get(id) ?? { x: 0, y: 0 },
        data: {
          label: node.entity.entityId,
          entityType: node.entity.entityType,
          subtitle: node.entity.owner,
          status: node.entity.lifecycle,
          depth: node.depth,
          tone: id === rootId ? "root" : "lineage",
        },
      };
    }),
    edges: lineage.subgraph.edges.map((edge) => ({
      id: edge.relationship.relationshipId,
      source: nodeKey(
        edge.relationship.sourceEntityType,
        edge.relationship.sourceEntityId,
      ),
      target: nodeKey(
        edge.relationship.targetEntityType,
        edge.relationship.targetEntityId,
      ),
      type: "decisionEdge",
      data: { label: edge.relationship.relationshipType },
    })),
  };
}

function evidenceDepths(graph: DecisionEvidenceGraph, rootId: string) {
  const adjacency = new Map<string, Set<string>>();
  graph.nodes.forEach((node) => {
    adjacency.set(nodeKey(node.entityType, node.entityId), new Set());
  });
  graph.edges.forEach((edge) => {
    const source = nodeKey(edge.sourceType, edge.sourceId);
    const target = nodeKey(edge.targetType, edge.targetId);
    adjacency.get(source)?.add(target);
    adjacency.get(target)?.add(source);
  });

  const depths = new Map<string, number>([[rootId, 0]]);
  const queue = [rootId];
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) {
      continue;
    }
    const nextDepth = (depths.get(current) ?? 0) + 1;
    for (const next of adjacency.get(current) ?? []) {
      if (!depths.has(next)) {
        depths.set(next, nextDepth);
        queue.push(next);
      }
    }
  }

  return depths;
}

function layoutByDepth(
  nodes: { id: string; depth: number; weight: number }[],
) {
  const byDepth = new Map<number, typeof nodes>();
  nodes.forEach((node) => {
    byDepth.set(node.depth, [...(byDepth.get(node.depth) ?? []), node]);
  });

  const positions = new Map<string, { x: number; y: number }>();
  [...byDepth.keys()].sort((left, right) => left - right).forEach((depth) => {
    const group = [...(byDepth.get(depth) ?? [])].sort((left, right) => {
      if (left.weight !== right.weight) {
        return left.weight - right.weight;
      }
      return left.id.localeCompare(right.id);
    });
    const totalHeight = Math.max(0, (group.length - 1) * 118);
    group.forEach((node, index) => {
      positions.set(node.id, {
        x: depth * 280 - 140,
        y: index * 118 - totalHeight / 2,
      });
    });
  });

  return positions;
}

function nodeKey(entityType: string, entityId: string) {
  return `${entityType}:${entityId}`;
}

function nodeWeight(entityType: EvidenceNode["entityType"]) {
  const order = [
    "GovernanceDecision",
    "Candidate",
    "EvaluationResult",
    "Metric",
    "DriftAnalysis",
    "Leaderboard",
    "Job",
    "MCPAudit",
    "Policy",
  ];
  const index = order.indexOf(entityType);
  return index === -1 ? order.length : index;
}
