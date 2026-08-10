from __future__ import annotations

from ai_governance.api.models.dashboard import (
    DashboardMetricResponse,
    DashboardSummaryResponse,
    PlatformHealthComponentResponse,
    RecentActivityItemResponse,
)
from ai_governance.services.dashboard_service import DashboardSummary


class DashboardApiMapper:
    """
    Converts dashboard read models into stable REST DTOs.
    """

    @staticmethod
    def to_response(summary: DashboardSummary) -> DashboardSummaryResponse:
        return DashboardSummaryResponse(
            governance_statistics=[
                DashboardMetricResponse(
                    label=metric.label,
                    value=metric.value,
                    description=metric.description,
                )
                for metric in summary.governance_statistics
            ],
            ontology_projection_statistics=[
                DashboardMetricResponse(
                    label=metric.label,
                    value=metric.value,
                    description=metric.description,
                )
                for metric in summary.ontology_projection_statistics
            ],
            platform_statistics=[
                DashboardMetricResponse(
                    label=metric.label,
                    value=metric.value,
                    description=metric.description,
                )
                for metric in summary.platform_statistics
            ],
            platform_health=[
                PlatformHealthComponentResponse(
                    component=component.component,
                    status=component.status,
                    detail=component.detail,
                )
                for component in summary.platform_health
            ],
            recent_activity=[
                RecentActivityItemResponse(
                    timestamp=item.timestamp,
                    resource=item.resource,
                    action=item.action,
                    status=item.status,
                )
                for item in summary.recent_activity
            ],
        )
