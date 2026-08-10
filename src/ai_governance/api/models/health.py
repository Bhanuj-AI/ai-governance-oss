from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """
    Response returned by health and readiness probes.
    """

    status: str = Field(
        description="Application health status.",
        examples=["UP"],
    )
