from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MCPMetrics:
    """
    In-process MCP metrics for observability.
    """

    tool_invocations_total: int = 0
    tool_failures_total: int = 0
    active_requests: int = 0
    rest_calls: int = 0
    rest_failures: int = 0
    tool_latency_ms: list[float] = field(default_factory=list)
    transport: str = "stdio"
    protocol_era_requests: dict[str, int] = field(default_factory=dict)

    def begin_tool(self) -> None:
        self.tool_invocations_total += 1
        self.active_requests += 1

    def finish_tool(self, latency_ms: float) -> None:
        self.active_requests -= 1
        self.tool_latency_ms.append(latency_ms)

    def fail_tool(self) -> None:
        self.tool_failures_total += 1

    def record_rest_call(self, failed: bool = False) -> None:
        self.rest_calls += 1
        if failed:
            self.rest_failures += 1

    def record_rest_failure(self) -> None:
        self.rest_failures += 1

    def record_protocol_era(self, era: str) -> None:
        """Record protocol-era adoption without retaining client request data."""
        self.protocol_era_requests[era] = self.protocol_era_requests.get(era, 0) + 1

    def snapshot(self) -> dict[str, object]:
        return {
            "tool_invocations_total": self.tool_invocations_total,
            "tool_failures_total": self.tool_failures_total,
            "active_requests": self.active_requests,
            "rest_calls": self.rest_calls,
            "rest_failures": self.rest_failures,
            "tool_latency_ms": list(self.tool_latency_ms),
            "transport": self.transport,
            "protocol_era_requests": dict(self.protocol_era_requests),
        }
