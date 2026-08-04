from __future__ import annotations

from pydantic import BaseModel, Field


class MetadataResponse(BaseModel):
    """
    Response describing the Kavach REST API surface.
    """

    name: str = Field(
        description="Product name.",
        examples=["Kavach"],
    )
    version: str = Field(
        description="Installed Kavach package version.",
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
