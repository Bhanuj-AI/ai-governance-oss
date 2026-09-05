from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DashboardMetricResponse(BaseModel):
    label: str
    value: int
    description: str | None = None


class PlatformHealthComponentResponse(BaseModel):
    component: str
    status: Literal["Healthy", "Warning", "Unavailable", "Unknown", "IN MEMORY"]
    detail: str | None = None


class DashboardMetricSectionResponse(BaseModel):
    key: str
    label: str
    metrics: list[DashboardMetricResponse]


class DashboardAttentionSignalResponse(BaseModel):
    label: str
    value: int
    detail: str


class RecentActivityItemResponse(BaseModel):
    timestamp: datetime
    resource: str
    action: str
    status: str


class DashboardSummaryResponse(BaseModel):
    """
    Dedicated read model consumed by the Studio home dashboard.
    """

    governance_statistics: list[DashboardMetricResponse]
    ontology_projection_statistics: list[DashboardMetricResponse]
    platform_statistics: list[DashboardMetricResponse]
    platform_health: list[PlatformHealthComponentResponse]
    recent_activity: list[RecentActivityItemResponse]
    operational_sections: list[DashboardMetricSectionResponse] = []
    attention_signals: list[DashboardAttentionSignalResponse] = []
    health_checked_at: datetime | None = None
