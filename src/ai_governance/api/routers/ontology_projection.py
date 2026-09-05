"""REST API for runtime ontology projection reconciliation.

Endpoints:
    POST /api/v1/agent-executions/{id}/projection/reconcile
    GET  /api/v1/agent-executions/{id}/projection
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ai_governance.api.dependencies.projection import (
    get_ontology_projection_service,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models.ontology_projection import (
    ProjectionReconcileResponse,
    ProjectionStatusResponse,
)
from ai_governance.services.ontology_projection_service import (
    OntologyProjectionService,
)
from ai_governance.tenancy.domain import TenantContext

router = APIRouter(
    prefix="/api/v1/agent-executions",
    tags=["Ontology projection"],
)


@router.get(
    "/{execution_id}/projection",
    response_model=ProjectionStatusResponse,
)
def get_projection_status(
    execution_id: str,
    service: Annotated[OntologyProjectionService, Depends(get_ontology_projection_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> ProjectionStatusResponse:
    """Get the projection status for an execution."""
    status_data = service.get_projection_status(
        execution_id, context.organization_id, context.project_id
    )

    return ProjectionStatusResponse(
        execution_id=status_data["execution_id"],
        status=status_data["status"],
        projection_version=status_data.get("projection_version"),
        source_version=status_data.get("source_version"),
        relationships_projected=status_data["relationships_projected"],
        unresolved_references=status_data["unresolved_references"],
        last_projected_at=status_data.get("last_projected_at"),
    )


@router.post(
    "/{execution_id}/projection/reconcile",
    response_model=ProjectionReconcileResponse,
    status_code=status.HTTP_200_OK,
)
def reconcile_projection(
    execution_id: str,
    service: Annotated[OntologyProjectionService, Depends(get_ontology_projection_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
) -> ProjectionReconcileResponse:
    """Reconcile (rebuild) the graph projection for an execution.

    If the existing projection is stale or failed, it is deleted and
    rebuilt from PostgreSQL source data. If the projection is current,
    returns the existing state.
    """
    try:
        projection = service.reconcile_execution(
            execution_id, context.organization_id, context.project_id
        )
    except Exception as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Projection reconciliation failed: {exc}",
        ) from exc

    return ProjectionReconcileResponse(
        execution_id=projection.execution_id,
        status=projection.status.value,
        projection_version=projection.projection_version,
        source_version=projection.source_version,
        relationships_projected=projection.relationships_projected,
        unresolved_references=projection.unresolved_count,
        last_projected_at=projection.last_projected_at,
    )
