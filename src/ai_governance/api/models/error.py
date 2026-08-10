from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """
    Standard REST error payload body.
    """

    code: str = Field(
        description="Stable machine-readable error code.",
        examples=["validation_error"],
    )
    message: str = Field(
        description="Human-readable error summary.",
        examples=["Request validation failed."],
    )
    details: Any | None = Field(
        default=None,
        description="Optional structured error details.",
    )


class ErrorResponse(BaseModel):
    """
    Standard REST error envelope.
    """

    error: ErrorBody
