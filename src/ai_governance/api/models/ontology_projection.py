"""Pydantic models for ontology projection API endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProjectionStatusResponse(BaseModel):
    """Lightweight projection status for an execution."""

    execution_id: str
    status: str  # NOT_FOUND | PENDING | PROJECTED | FAILED
    projection_version: str | None = None
    source_version: int | None = None
    relationships_projected: int = 0
    unresolved_references: int = 0
    last_projected_at: datetime | None = None


class ProjectionReconcileResponse(BaseModel):
    """Response after reconciling a projection."""

    execution_id: str
    status: str
    projection_version: str
    source_version: int
    relationships_projected: int
    unresolved_references: int
    last_projected_at: datetime | None = None


class ProjectionBatchResponse(BaseModel):
    """Response for batch reconciliation."""

    reconciled: int
    failed: int
    not_found: int = 0
