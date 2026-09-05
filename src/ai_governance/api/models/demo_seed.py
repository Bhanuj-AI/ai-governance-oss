from __future__ import annotations

from pydantic import BaseModel, Field


class DemoSeedResponse(BaseModel):
    """Result of an idempotent local demo-data seed."""

    seeded: bool = Field(description="Whether the local demo seed completed.")
    decision_ids: list[str] = Field(
        description="Governance decisions ensured by the demo seed."
    )


class AgentRuntimeDemoStatusResponse(BaseModel):
    """Availability of the complete local Agent Runtime sample."""

    seeded: bool = Field(description="Whether the full Agent Runtime sample is available.")
