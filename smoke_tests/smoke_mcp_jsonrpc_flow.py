from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.mcp.clients import RestClient, RestClientError
from ai_governance.mcp.server import create_server


def main() -> None:
    client = TestClient(create_app())
    mcp_server = create_server(
        RestClient(
            base_url="http://testserver",
            transport=_test_client_transport(client),
        ),
        audit_log=MCPExecutionAuditLog.in_memory(),
    )

    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "provider.list",
                "arguments": {},
            },
        },
    ]

    for message in messages:
        response = mcp_server.handle_json_rpc(message)
        print("[request]")
        print(json.dumps(message, indent=2, sort_keys=True))
        print("[response]")
        print(json.dumps(_summarize_response(response), indent=2, sort_keys=True))
        print()


def _test_client_transport(
    client: TestClient,
):
    def transport(
        method: str,
        path: str,
        query: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> Any:
        response = client.request(method, path, params=query, json=body)
        if response.status_code >= 400:
            raise RestClientError(
                status_code=response.status_code,
                payload=response.json(),
            )
        return response.json()

    return transport


def _summarize_response(
    response: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if response is None:
        return None

    result = response.get("result")
    if isinstance(result, dict) and "tools" in result:
        tools = result["tools"]
        return {
            **response,
            "result": {
                "tool_count": len(tools),
                "tool_names": [tool["name"] for tool in tools],
            },
        }

    if isinstance(result, dict) and "content" in result:
        content = result["content"][0]
        tool_payload = json.loads(content["text"])
        return {
            **response,
            "result": {
                "isError": result["isError"],
                "tool": tool_payload["tool"],
                "status": tool_payload["status"],
                "data_preview": tool_payload["data"],
            },
        }

    return response


if __name__ == "__main__":
    main()
