from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TelemetryStatusResponse(BaseModel):
    mode: str
    installation_id: str
    enabled_categories: list[str]
    exporter: str
    last_export_status: str | None
    last_successful_export: datetime | None
    pending_snapshots: int
    operational_metrics: dict[str, int | float]


class TelemetryPreviewResponse(BaseModel):
    payloads: list[dict[str, Any]]
