from __future__ import annotations

from pydantic import BaseModel, Field


class MetadataResponse(BaseModel):
    """
    Response describing the AI Governance Control Plane REST API surface.
    """

    name: str = Field(
        description="Product name.",
        examples=["AI Governance Control Plane"],
    )
    version: str = Field(
        description="Installed AI Governance Control Plane package version.",
        examples=["1.0.6"],
    )
    api_version: str = Field(
        description="REST API version.",
        examples=["v1"],
    )
    timezone: str = Field(
        description="Configured display timezone.",
        examples=["UTC"],
    )
