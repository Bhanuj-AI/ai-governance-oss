"""Command-line launcher for AI Governance Control Plane MCP transports."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from ai_governance.mcp.server import get_mcp_settings
from ai_governance.mcp.transports.streamable_http import create_mcp_http_app


def main() -> None:
    # Match the existing local MCP launcher. Explicit process environment
    # values continue to win, while host-local invocations pick up Keycloak and
    # Streamable HTTP settings from the repository's ignored development file.
    load_dotenv(Path(".env.local"), override=False)
    parser = argparse.ArgumentParser(prog="ai-governance-mcp")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"))
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    arguments = parser.parse_args()
    settings = get_mcp_settings()
    transport = arguments.transport or settings.transport
    if transport == "stdio":
        from ai_governance.mcp.server import create_server

        create_server().run_stdio()
        return

    host = arguments.host or settings.http_host
    port = arguments.port or settings.http_port
    uvicorn.run(create_mcp_http_app(settings=settings), host=host, port=port)
