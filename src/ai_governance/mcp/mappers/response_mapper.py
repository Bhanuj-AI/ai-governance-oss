from __future__ import annotations

from typing import Any


class MCPResponseMapper:
    """
    Maps REST DTO payloads to MCP tool result data.

    Deliberately keeps this mapper transparent so REST remains the
    canonical public DTO contract.
    """

    @staticmethod
    def from_rest_payload(payload: Any) -> Any:
        return payload
