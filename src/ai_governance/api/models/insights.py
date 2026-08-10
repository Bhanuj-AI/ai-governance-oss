from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class GovernanceInsightResponse(BaseModel):
    """
    Evidence-first response for insights and investigations.
    """

    summary: str
    status: Literal["SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN"]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    related_resources: list[dict[str, Any]] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    generated_at: datetime


class GovernanceEvidenceReportResponse(BaseModel):
    """
    Generated governance evidence report.
    """

    report_type: str
    report_format: Literal["json", "markdown"]
    content: dict[str, Any] | str
    generated_at: datetime
