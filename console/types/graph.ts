export type GraphEntity = {
  entityId: string;
  entityType: string;
  lifecycle: string;
  owner: string;
  ontologyVersion: string;
  createdAt: string;
  metadata: Record<string, unknown>;
  immutableAttributes: Record<string, unknown>;
  mutableAttributes: Record<string, unknown>;
};

export type GraphRelationship = {
  relationshipId: string;
  relationshipType: string;
  sourceEntityId: string;
  sourceEntityType: string;
  targetEntityId: string;
  targetEntityType: string;
  ontologyVersion: string;
  createdAt: string;
  createdBy: string;
  metadata: Record<string, unknown>;
};

export type GraphNode = {
  entity: GraphEntity;
  depth: number;
};

export type GraphEdge = {
  relationship: GraphRelationship;
};

export type GraphSubgraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type GraphPath = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type GraphRelationshipPage = {
  items: GraphRelationship[];
  limit: number;
  nextCursor: string | null;
};

export type GraphEntityPage = {
  items: GraphEntity[];
  limit: number;
  nextCursor: string | null;
};

export type GraphPathList = {
  paths: GraphPath[];
};

export type RelationshipDirection = "incoming" | "outgoing" | "both";

export type NeighbourhoodRequest = {
  entityType: string;
  entityId: string;
  depth?: number;
  relationshipTypes?: string[];
  entityTypes?: string[];
  limit?: number;
};

export type RelationshipListRequest = {
  entityType: string;
  entityId: string;
  direction?: RelationshipDirection;
  relationshipType?: string;
  limit?: number;
  cursor?: string;
};

export type TraversalRequest = {
  entityType: string;
  entityId: string;
  depth?: number;
  relationshipTypes?: string[];
  limit?: number;
};

export type PathRequest = {
  sourceType: string;
  sourceId: string;
  targetType: string;
  targetId: string;
  maxDepth?: number;
  relationshipTypes?: string[];
  limit?: number;
};

export type GraphEntityDto = {
  entity_id: string;
  entity_type: string;
  lifecycle: string;
  owner: string;
  ontology_version: string;
  created_at: string;
  metadata: Record<string, unknown>;
  immutable_attributes: Record<string, unknown>;
  mutable_attributes: Record<string, unknown>;
};

export type GraphRelationshipDto = {
  relationship_id: string;
  relationship_type: string;
  source_entity_id: string;
  source_entity_type: string;
  target_entity_id: string;
  target_entity_type: string;
  ontology_version: string;
  created_at: string;
  created_by: string;
  metadata: Record<string, unknown>;
};

export type GraphNodeDto = {
  entity: GraphEntityDto;
  depth: number;
};

export type GraphEdgeDto = {
  relationship: GraphRelationshipDto;
};

export type GraphSubgraphDto = {
  nodes: GraphNodeDto[];
  edges: GraphEdgeDto[];
};

export type GraphPathDto = {
  nodes: GraphNodeDto[];
  edges: GraphEdgeDto[];
};

export type GraphRelationshipPageDto = {
  items: GraphRelationshipDto[];
  limit: number;
  next_cursor: string | null;
};

export type GraphEntityPageDto = {
  items: GraphEntityDto[];
  limit: number;
  next_cursor: string | null;
};

export type GraphPathListDto = {
  paths: GraphPathDto[];
};
