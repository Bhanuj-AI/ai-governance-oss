from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from ai_governance.mcp.dto import ToolDescription
from ai_governance.mcp.runtime_context import get_runtime_context
from ai_governance.tenancy.domain import ActorType

ToolHandler = Callable[[BaseModel], Any]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    request_model: type[BaseModel]
    handler: ToolHandler

    def describe(self) -> ToolDescription:
        return ToolDescription(
            name=self.name,
            description=self.description,
            input_schema=self.request_model.model_json_schema(),
        )


class ToolRegistry:
    """
    In-memory MCP tool registry populated during server startup.
    """

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        request_model: type[BaseModel],
        handler: ToolHandler,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")

        self._tools[name] = RegisteredTool(
            name=name,
            description=description,
            request_model=request_model,
            handler=handler,
        )

    def list_tools(self) -> list[ToolDescription]:
        return [
            tool.describe()
            for tool in sorted(
                self._tools.values(),
                key=lambda tool: tool.name,
            )
        ]

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Tool '{name}' is not registered.") from exc

    def call(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        tool = self.get(name)
        request = tool.request_model.model_validate(
            _authenticated_payload(payload or {})
        )
        return tool.handler(request)


def _authenticated_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Ensure remote controlled-write metadata cannot impersonate a caller."""
    runtime = get_runtime_context()
    if runtime is None or runtime.principal is None:
        return payload
    normalized = dict(payload)
    if "requested_by" in normalized:
        normalized["requested_by"] = runtime.principal.subject
    if "actor_type" in normalized:
        normalized["actor_type"] = {
            ActorType.USER: "HUMAN",
            ActorType.SERVICE: "SERVICE",
            ActorType.SYSTEM: "SERVICE",
        }[runtime.principal.principal_type]
    return normalized
