from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.mcp.clients import RestClient, RestClientError
from ai_governance.mcp.server import create_server


def main() -> None:
    app = create_app()
    client = TestClient(app)
    evaluation_id, execution_id = _seed_evaluation(client)
    experiment_id = _seed_experiment(client)
    mcp_server = create_server(
        RestClient(
            base_url="http://testserver",
            transport=_test_client_transport(client),
        ),
        audit_log=MCPExecutionAuditLog.in_memory(),
    )

    checks = {
        "provider.list": mcp_server.call_tool("provider.list"),
        "evaluation.latest": mcp_server.call_tool(
            "evaluation.latest",
            {"execution_id": execution_id},
        ),
        "evaluation.history": mcp_server.call_tool(
            "evaluation.history",
            {"execution_id": execution_id},
        ),
        "evaluation.metrics": mcp_server.call_tool(
            "evaluation.metrics",
            {"evaluation_id": evaluation_id},
        ),
        "experiment.list": mcp_server.call_tool("experiment.list"),
        "experiment.get": mcp_server.call_tool(
            "experiment.get",
            {"experiment_id": experiment_id},
        ),
    }

    for name, result in checks.items():
        _assert_tool_ok(result)
        print(f"[{name}] status={result.status}")
        if name == "provider.list":
            print(f"providers={[provider['name'] for provider in result.data]}")
        elif name == "evaluation.history":
            print(f"records={len(result.data['evaluations'])}")
        elif name.startswith("evaluation."):
            print(f"evaluation_id={result.data['evaluation_id']}")
            print(f"provider={result.data['provider_name']}")
        elif name == "experiment.list":
            print(f"experiments={len(result.data)}")
        else:
            print(f"experiment_id={result.data['experiment_id']}")
            print(f"name={result.data['name']}")
        print()


def _seed_evaluation(
    client: TestClient,
) -> tuple[str, str]:
    execution_id = "execution-read-1"
    response = client.post(
        "/api/v1/evaluations",
        json={
            "provider_name": "mock",
            "workflow_id": "claim-validation",
            "workflow_name": "Claim Validation",
            "workflow_version": "1.0.0",
            "execution_id": execution_id,
            "execution_status": "COMPLETED",
            "input": {"question": "Was the claim valid?"},
            "final_state": {"answer": "The claim appears valid."},
            "events": [{"event_type": "WORKFLOW_COMPLETED"}],
            "metric_specs": [{"name": "answer_relevance"}],
            "provider_config": {"api_key": "should-not-leak"},
        },
    )
    _assert_http_status(response.status_code, 201, response.json())
    return str(response.json()["evaluation_id"]), execution_id


def _seed_experiment(
    client: TestClient,
) -> str:
    response = client.post(
        "/api/v1/experiments",
        json={
            "name": "smoke-read-experiment",
            "description": "Seeded experiment for MCP read tool smoke tests.",
            "metadata": {"owner": "smoke-test"},
        },
    )
    _assert_http_status(response.status_code, 201, response.json())
    return str(response.json()["experiment_id"])


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


def _assert_tool_ok(result) -> None:
    if result.status != "ok":
        raise AssertionError(result.error)


def _assert_http_status(
    actual: int,
    expected: int,
    payload: dict[str, Any],
) -> None:
    if actual != expected:
        raise AssertionError(
            f"Expected HTTP {expected}, got {actual}: {payload}",
        )


if __name__ == "__main__":
    main()
