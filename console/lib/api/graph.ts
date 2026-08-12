import { aiGovernanceRequest } from "@/lib/api/client";
import type {
  GraphEntity,
  GraphEntityDto,
  GraphPath,
  GraphPathDto,
  GraphPathList,
  GraphPathListDto,
  GraphRelationship,
  GraphRelationshipDto,
  GraphRelationshipPage,
  GraphRelationshipPageDto,
  GraphSubgraph,
  GraphSubgraphDto,
  NeighbourhoodRequest,
  PathRequest,
  RelationshipListRequest,
  TraversalRequest,
} from "@/types/graph";

export async function getEntity(entityType: string, entityId: string) {
  const dto = await aiGovernanceRequest<GraphEntityDto>(
    `/api/v1/ontology/entities/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
  );
  return mapEntity(dto);
}

export async function getRelationships(request: RelationshipListRequest) {
  const dto = await aiGovernanceRequest<GraphRelationshipPageDto>(
    `/api/v1/ontology/entities/${encodeURIComponent(request.entityType)}/${encodeURIComponent(request.entityId)}/relationships`,
    {
      direction: request.direction,
      relationship_type: request.relationshipType,
      limit: request.limit,
      cursor: request.cursor,
    },
  );
  return mapRelationshipPage(dto);
}

export async function getNeighbourhood(request: NeighbourhoodRequest) {
  const dto = await aiGovernanceRequest<GraphSubgraphDto>(
    `/api/v1/ontology/entities/${encodeURIComponent(request.entityType)}/${encodeURIComponent(request.entityId)}/neighbourhood`,
    {
      depth: request.depth,
      relationship_type: request.relationshipTypes,
      entity_type: request.entityTypes,
      limit: request.limit,
    },
  );
  return mapSubgraph(dto);
}

export async function getUpstream(request: TraversalRequest) {
  const dto = await aiGovernanceRequest<GraphSubgraphDto>(
    `/api/v1/ontology/entities/${encodeURIComponent(request.entityType)}/${encodeURIComponent(request.entityId)}/upstream`,
    {
      depth: request.depth,
      relationship_type: request.relationshipTypes,
      limit: request.limit,
    },
  );
  return mapSubgraph(dto);
}

export async function getDownstream(request: TraversalRequest) {
  const dto = await aiGovernanceRequest<GraphSubgraphDto>(
    `/api/v1/ontology/entities/${encodeURIComponent(request.entityType)}/${encodeURIComponent(request.entityId)}/downstream`,
    {
      depth: request.depth,
      relationship_type: request.relationshipTypes,
      limit: request.limit,
    },
  );
  return mapSubgraph(dto);
}

export async function findPaths(request: PathRequest) {
  const dto = await aiGovernanceRequest<GraphPathListDto>("/api/v1/ontology/path", {
    source_type: request.sourceType,
    source_id: request.sourceId,
    target_type: request.targetType,
    target_id: request.targetId,
    max_depth: request.maxDepth,
    relationship_type: request.relationshipTypes,
    limit: request.limit,
  });
  return mapPathList(dto);
}

export function mapEntity(dto: GraphEntityDto): GraphEntity {
  return {
    entityId: dto.entity_id,
    entityType: dto.entity_type,
    lifecycle: dto.lifecycle,
    owner: dto.owner,
    ontologyVersion: dto.ontology_version,
    createdAt: dto.created_at,
    metadata: dto.metadata,
    immutableAttributes: dto.immutable_attributes,
    mutableAttributes: dto.mutable_attributes,
  };
}

function mapRelationship(dto: GraphRelationshipDto): GraphRelationship {
  return {
    relationshipId: dto.relationship_id,
    relationshipType: dto.relationship_type,
    sourceEntityId: dto.source_entity_id,
    sourceEntityType: dto.source_entity_type,
    targetEntityId: dto.target_entity_id,
    targetEntityType: dto.target_entity_type,
    ontologyVersion: dto.ontology_version,
    createdAt: dto.created_at,
    createdBy: dto.created_by,
    metadata: dto.metadata,
  };
}

export function mapSubgraph(dto: GraphSubgraphDto): GraphSubgraph {
  const edgesByRelationshipId = new Map<string, { relationship: GraphRelationship }>();
  for (const edge of dto.edges) {
    const relationship = mapRelationship(edge.relationship);
    edgesByRelationshipId.set(relationship.relationshipId, { relationship });
  }

  return {
    nodes: dto.nodes.map((node) => ({
      entity: mapEntity(node.entity),
      depth: node.depth,
    })),
    edges: [...edgesByRelationshipId.values()],
  };
}

function mapRelationshipPage(
  dto: GraphRelationshipPageDto,
): GraphRelationshipPage {
  return {
    items: dto.items.map(mapRelationship),
    limit: dto.limit,
    nextCursor: dto.next_cursor,
  };
}

function mapPath(dto: GraphPathDto): GraphPath {
  return {
    nodes: dto.nodes.map((node) => ({
      entity: mapEntity(node.entity),
      depth: node.depth,
    })),
    edges: dto.edges.map((edge) => ({
      relationship: mapRelationship(edge.relationship),
    })),
  };
}

function mapPathList(dto: GraphPathListDto): GraphPathList {
  return {
    paths: dto.paths.map(mapPath),
  };
}
