from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ai_governance.api.dependencies import (
    get_governance_decision_repository,
    get_job_repository,
    get_mcp_audit_log,
    get_ontology_graph_query_service,
    get_ontology_graph_repository,
    get_policy_administration_repository,
)
from ai_governance.api.models import (
    ErrorResponse,
    GraphEntityResponse,
    GraphPathListResponse,
    GraphRelationshipPageResponse,
    GraphRelationshipResponse,
    GraphSubgraphResponse,
)
from ai_governance.ontology import OntologyGraphQueryService
from ai_governance.ontology.demo_seed import (
    DEMO_ENTITY_ID,
    DEMO_ENTITY_TYPE,
    demo_governance_decision_service,
    seed_demo_jobs,
    seed_demo_mcp_audit_log,
    seed_demo_ontology_graph,
    seed_demo_ontology_graph_decision,
    seed_demo_policy_administration,
)

router = APIRouter(
    prefix="/api/v1/ontology",
    tags=["Ontology Graph"],
)


@router.post(
    "/demo/seed",
    response_model=GraphSubgraphResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Seed demo ontology graph",
    description=(
        "Seed a small valid ontology graph for local console visualization "
        "and return the seeded Candidate neighbourhood."
    ),
)
def seed_demo_graph(
    repository: Annotated[
        object,
        Depends(get_ontology_graph_repository),
    ],
    service: Annotated[
        OntologyGraphQueryService,
        Depends(get_ontology_graph_query_service),
    ],
    decision_repository: Annotated[
        object,
        Depends(get_governance_decision_repository),
    ],
    policy_repository: Annotated[
        object,
        Depends(get_policy_administration_repository),
    ],
    job_repository: Annotated[
        object,
        Depends(get_job_repository),
    ],
    audit_log: Annotated[
        object,
        Depends(get_mcp_audit_log),
    ],
) -> GraphSubgraphResponse:
    seed_demo_ontology_graph(repository)
    seed_demo_policy_administration(policy_repository)
    seed_demo_jobs(job_repository)
    seed_demo_mcp_audit_log(audit_log)
    seed_demo_ontology_graph_decision(
        repository,
        demo_governance_decision_service(
            decision_repository=decision_repository,
            graph_query_service=service,
        ),
    )
    return GraphSubgraphResponse.from_domain(
        service.get_neighbourhood(
            DEMO_ENTITY_TYPE,
            DEMO_ENTITY_ID,
            depth=2,
            limit=100,
        )
    )


@router.get(
    "/entities/{entity_type}/{entity_id}",
    response_model=GraphEntityResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get ontology entity",
    description="Return one ontology graph entity by type and ID.",
)
def get_entity(
    entity_type: str,
    entity_id: str,
    service: Annotated[
        OntologyGraphQueryService,
        Depends(get_ontology_graph_query_service),
    ],
) -> GraphEntityResponse:
    entity = service.get_entity(entity_type, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ontology entity '{entity_type}/{entity_id}' was not found.",
        )
    return GraphEntityResponse.from_domain(entity)


@router.get(
    "/relationships/{relationship_id}",
    response_model=GraphRelationshipResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get ontology relationship",
    description="Return one ontology graph relationship by ID.",
)
def get_relationship(
    relationship_id: str,
    service: Annotated[
        OntologyGraphQueryService,
        Depends(get_ontology_graph_query_service),
    ],
) -> GraphRelationshipResponse:
    relationship = service.get_relationship(relationship_id)
    if relationship is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ontology relationship '{relationship_id}' was not found.",
        )
    return GraphRelationshipResponse.from_domain(relationship)


@router.get(
    "/entities/{entity_type}/{entity_id}/relationships",
    response_model=GraphRelationshipPageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="List ontology relationships",
    description="Return relationships connected to an ontology entity.",
)
def find_relationships(
    entity_type: str,
    entity_id: str,
    service: Annotated[
        OntologyGraphQueryService,
        Depends(get_ontology_graph_query_service),
    ],
    direction: str | None = None,
    relationship_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = None,
) -> GraphRelationshipPageResponse:
    return GraphRelationshipPageResponse.from_domain(
        service.find_relationships(
            entity_type,
            entity_id,
            direction=direction,
            relationship_type=relationship_type,
            limit=limit,
            cursor=cursor,
        )
    )


@router.get(
    "/entities/{entity_type}/{entity_id}/neighbourhood",
    response_model=GraphSubgraphResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get ontology neighbourhood",
    description="Return a bounded neighbourhood around an ontology entity.",
)
def get_neighbourhood(
    entity_type: str,
    entity_id: str,
    service: Annotated[
        OntologyGraphQueryService,
        Depends(get_ontology_graph_query_service),
    ],
    depth: int = Query(default=1, ge=1, le=5),
    relationship_type: list[str] | None = Query(default=None),
    entity_type_filter: list[str] | None = Query(
        default=None,
        alias="entity_type",
    ),
    limit: int = Query(default=100, ge=1, le=500),
) -> GraphSubgraphResponse:
    return GraphSubgraphResponse.from_domain(
        service.get_neighbourhood(
            entity_type,
            entity_id,
            depth=depth,
            relationship_types=relationship_type,
            entity_types=entity_type_filter,
            limit=limit,
        )
    )


@router.get(
    "/entities/{entity_type}/{entity_id}/upstream",
    response_model=GraphSubgraphResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get upstream ontology lineage",
    description="Return bounded upstream lineage for an ontology entity.",
)
def get_upstream(
    entity_type: str,
    entity_id: str,
    service: Annotated[
        OntologyGraphQueryService,
        Depends(get_ontology_graph_query_service),
    ],
    depth: int = Query(default=1, ge=1, le=5),
    relationship_type: list[str] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> GraphSubgraphResponse:
    return GraphSubgraphResponse.from_domain(
        service.get_upstream_lineage(
            entity_type,
            entity_id,
            depth=depth,
            relationship_types=relationship_type,
            limit=limit,
        )
    )


@router.get(
    "/entities/{entity_type}/{entity_id}/downstream",
    response_model=GraphSubgraphResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get downstream ontology impact",
    description="Return bounded downstream impact for an ontology entity.",
)
def get_downstream(
    entity_type: str,
    entity_id: str,
    service: Annotated[
        OntologyGraphQueryService,
        Depends(get_ontology_graph_query_service),
    ],
    depth: int = Query(default=1, ge=1, le=5),
    relationship_type: list[str] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> GraphSubgraphResponse:
    return GraphSubgraphResponse.from_domain(
        service.get_downstream_impact(
            entity_type,
            entity_id,
            depth=depth,
            relationship_types=relationship_type,
            limit=limit,
        )
    )


@router.get(
    "/path",
    response_model=GraphPathListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Find ontology graph paths",
    description="Return bounded paths between two ontology entities.",
)
def find_paths(
    service: Annotated[
        OntologyGraphQueryService,
        Depends(get_ontology_graph_query_service),
    ],
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    max_depth: int = Query(default=5, ge=1, le=5),
    relationship_type: list[str] | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=500),
) -> GraphPathListResponse:
    return GraphPathListResponse.from_domain(
        service.find_paths(
            source_type,
            source_id,
            target_type,
            target_id,
            max_depth=max_depth,
            relationship_types=relationship_type,
            limit=limit,
        )
    )
