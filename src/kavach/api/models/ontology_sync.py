from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from kavach.ontology.synchronization import OntologySyncEventStatus


class OntologySyncEventResponse(BaseModel):
    """
    REST representation of an ontology synchronization event.
    """

    model_config = ConfigDict(use_enum_values=True)

    event_id: str
    event_type: str
    entity_type: str
    entity_id: str | None = None
    scope_identifier: str | None = None
    correlation_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: OntologySyncEventStatus
    retry_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    next_retry_at: datetime | None = None
    last_error: str | None = None
    failed_at: datetime | None = None
    reconciliation_report: dict[str, Any] | None = None


class OntologySyncEventListResponse(BaseModel):
    """
    List response for ontology synchronization events.
    """

    events: list[OntologySyncEventResponse]


class OntologySyncMetricsResponse(BaseModel):
    """
    Aggregate operational metrics for ontology synchronization events.
    """

    total_events: int
    pending_events: int
    processing_events: int
    completed_events: int
    failed_events: int
    dead_letter_events: int
    cancelled_events: int
