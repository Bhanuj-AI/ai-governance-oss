from __future__ import annotations

from kavach.api.models import (
    GovernanceEvidenceReportResponse,
    GovernanceInsightResponse,
)
from kavach.services.governance_insights import (
    GovernanceInsight,
    GovernanceReport,
)


class GovernanceInsightApiMapper:
    """
    Convert Phase 3 insight service models into REST DTOs.
    """

    @staticmethod
    def to_insight_response(
        insight: GovernanceInsight,
    ) -> GovernanceInsightResponse:
        return GovernanceInsightResponse(
            summary=insight.summary,
            status=insight.status,
            confidence=insight.confidence,
            evidence=insight.evidence,
            metrics=insight.metrics,
            related_resources=insight.related_resources,
            recommended_next_steps=insight.recommended_next_steps,
            generated_at=insight.generated_at,
        )

    @staticmethod
    def to_report_response(
        report: GovernanceReport,
    ) -> GovernanceEvidenceReportResponse:
        return GovernanceEvidenceReportResponse(
            report_type=report.report_type,
            report_format=report.report_format,
            content=report.content,
            generated_at=report.generated_at,
        )
