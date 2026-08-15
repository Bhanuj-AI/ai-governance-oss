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
export type DecisionLineageLayout = "sequence" | "depth";

type LayoutNode = {
  id: string;
  depth: number;
  entityType: string;
  weight: number;
};
type LayoutRelationship = { source: string; target: string };

export function evidenceGraphToFlow(
  graph: DecisionEvidenceGraph,
): { nodes: DecisionFlowNode[]; edges: DecisionFlowEdge[] } {
  const rootId = nodeKey(graph.targetType, graph.targetId);
  const depths = evidenceDepths(graph, rootId);
  const positions = layoutByDepth(
    graph.nodes.map((node) => ({
      id: nodeKey(node.entityType, node.entityId),
      depth: depths.get(nodeKey(node.entityType, node.entityId)) ?? 1,
      entityType: node.entityType,
      weight: nodeWeight(node.entityType),
    })),
    graph.edges.map((edge) => ({
      source: nodeKey(edge.sourceType, edge.sourceId),
      target: nodeKey(edge.targetType, edge.targetId),
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
  layout: DecisionLineageLayout = "sequence",
): { nodes: DecisionFlowNode[]; edges: DecisionFlowEdge[] } {
  const rootId = nodeKey("GovernanceDecision", lineage.decision.decisionId);
  const layoutNodes = lineage.subgraph.nodes.map((node) => ({
    id: nodeKey(node.entity.entityType, node.entity.entityId),
    depth: node.depth,
    entityType: node.entity.entityType,
    weight: nodeWeight(node.entity.entityType),
  }));
  const relationships = lineage.subgraph.edges.map((edge) => ({
    source: nodeKey(
      edge.relationship.sourceEntityType,
      edge.relationship.sourceEntityId,
    ),
    target: nodeKey(
      edge.relationship.targetEntityType,
      edge.relationship.targetEntityId,
    ),
  }));
  const positions = layout === "sequence"
    ? layoutBySequence(layoutNodes, relationships, rootId)
    : layoutByDepth(layoutNodes, relationships);

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

function layoutByDepth(nodes: LayoutNode[], relationships: LayoutRelationship[]) {
  const byDepth = new Map<number, typeof nodes>();
  nodes.forEach((node) => {
    byDepth.set(node.depth, [...(byDepth.get(node.depth) ?? []), node]);
  });

  const sortedDepths = [...byDepth.keys()].sort((left, right) => left - right);
  const orderedByDepth = new Map<number, LayoutNode[]>();
  const depthByNodeId = new Map(nodes.map((node) => [node.id, node.depth]));
  const connectedNodeIds = new Map<string, Set<string>>();

  for (const relationship of relationships) {
    connectedNodeIds.set(
      relationship.source,
      new Set([...(connectedNodeIds.get(relationship.source) ?? []), relationship.target]),
    );
    connectedNodeIds.set(
      relationship.target,
      new Set([...(connectedNodeIds.get(relationship.target) ?? []), relationship.source]),
    );
  }

  for (const depth of sortedDepths) {
    orderedByDepth.set(depth, [...(byDepth.get(depth) ?? [])].sort(compareLayoutNodes));
  }

  for (let pass = 0; pass < 3; pass += 1) {
    for (let index = 1; index < sortedDepths.length; index += 1) {
      orderLayerByNeighbours(sortedDepths[index], sortedDepths[index - 1], orderedByDepth, depthByNodeId, connectedNodeIds);
    }
    for (let index = sortedDepths.length - 2; index > 0; index -= 1) {
      orderLayerByNeighbours(sortedDepths[index], sortedDepths[index + 1], orderedByDepth, depthByNodeId, connectedNodeIds);
    }
  }

  const positions = new Map<string, { x: number; y: number }>();
  sortedDepths.forEach((depth) => {
    const group = orderedByDepth.get(depth) ?? [];
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

function layoutBySequence(nodes: LayoutNode[], relationships: LayoutRelationship[], rootId: string) {
  return layoutByDepth(
    nodes.map((node) => ({ ...node, depth: sequenceForLineageNode(node, rootId) })),
    relationships,
  );
}

function sequenceForLineageNode(node: LayoutNode, rootId: string) {
  if (node.id === rootId) return 4;
  if (["PromptVersion", "ModelVersion", "DatasetVersion", "EvaluationProvider"].includes(node.entityType)) return 0;
  if (["Experiment", "Candidate"].includes(node.entityType)) return 1;
  if (["Job", "EvaluationRun", "EvaluationResult", "Metric", "DriftAnalysis", "Leaderboard"].includes(node.entityType)) return 2;
  if (["Policy", "Actor", "MCPAudit"].includes(node.entityType)) return 3;
  if (node.entityType === "GovernanceDecision") return 5;
  return 3;
}

function orderLayerByNeighbours(
  depth: number,
  neighbourDepth: number,
  orderedByDepth: Map<number, LayoutNode[]>,
  depthByNodeId: Map<string, number>,
  connectedNodeIds: Map<string, Set<string>>,
) {
  const layer = orderedByDepth.get(depth);
  const neighbourLayer = orderedByDepth.get(neighbourDepth);
  if (!layer || !neighbourLayer || layer.length < 2) return;

  const neighbourOrder = new Map(neighbourLayer.map((node, index) => [node.id, index]));
  const baseOrder = new Map(layer.map((node, index) => [node.id, index]));
  layer.sort((left, right) => {
    const leftRank = averageConnectedRank(left.id, neighbourDepth, depthByNodeId, connectedNodeIds, neighbourOrder);
    const rightRank = averageConnectedRank(right.id, neighbourDepth, depthByNodeId, connectedNodeIds, neighbourOrder);
    if (leftRank !== undefined && rightRank !== undefined && leftRank !== rightRank) return leftRank - rightRank;
    if (leftRank !== undefined && rightRank === undefined) return -1;
    if (leftRank === undefined && rightRank !== undefined) return 1;
    return (baseOrder.get(left.id) ?? 0) - (baseOrder.get(right.id) ?? 0);
  });
}

function averageConnectedRank(
  nodeId: string,
  neighbourDepth: number,
  depthByNodeId: Map<string, number>,
  connectedNodeIds: Map<string, Set<string>>,
  neighbourOrder: Map<string, number>,
) {
  const ranks = [...(connectedNodeIds.get(nodeId) ?? [])]
    .filter((connectedId) => depthByNodeId.get(connectedId) === neighbourDepth)
    .map((connectedId) => neighbourOrder.get(connectedId))
    .filter((rank): rank is number => rank !== undefined);
  if (!ranks.length) return undefined;
  return ranks.reduce((total, rank) => total + rank, 0) / ranks.length;
}

function compareLayoutNodes(left: LayoutNode, right: LayoutNode) {
  if (left.weight !== right.weight) return left.weight - right.weight;
  return left.id.localeCompare(right.id);
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
