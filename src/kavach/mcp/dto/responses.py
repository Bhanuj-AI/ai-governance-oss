from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolDescription(BaseModel):
    """
    Public MCP tool description.
    """

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """
    Transport-neutral result for an MCP tool invocation.
    """

    tool: str
    status: str
    data: Any | None = None
    error: dict[str, Any] | None = None
    request_id: str
