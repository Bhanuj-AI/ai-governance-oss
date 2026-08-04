from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

from kavach.api.app import create_app
from kavach.api.dependencies import get_mcp_audit_log
from kavach.mcp.audit import MCPExecutionAuditLog
from kavach.mcp.clients import RestClient, RestClientError
from kavach.mcp.server import create_server


def main() -> None:
    args = _parse_args()

    with _audit_database_path(args.audit_db) as database_path:
        audit_log = MCPExecutionAuditLog.sqlite(database_path)
        app = create_app()
        app.dependency_overrides[get_mcp_audit_log] = lambda: audit_log
        client = TestClient(app)
        mcp_server = create_server(
            RestClient(
                base_url="http://testserver",
                transport=_test_client_transport(client),
            ),
            audit_log=audit_log,
        )

        evaluation = mcp_server.call_tool(
            "evaluation.submit_async",
            {
                **_write_envelope(
                    request_id="request-write-evaluation",
                    correlation_id="corr-write",
                    idempotency_key="idem-write-evaluation",
                ),
                "provider_name": "mock",
                "workflow_id": "claim-validation",
                "workflow_name": "Claim Validation",
                "workflow_version": "1.0.0",
                "execution_id": "execution-write-1",
                "execution_status": "COMPLETED",
                "input": {"question": "Was the claim valid?"},
                "final_state": {"answer": "The claim appears valid."},
                "events": [{"event_type": "WORKFLOW_COMPLETED"}],
                "metric_specs": [{"name": "answer_relevance"}],
                "provider_config": {"api_key": "should-not-leak"},
            },
        )
        _assert_tool_ok(evaluation)
        evaluation_job_id = evaluation.data["job_id"]

        job_status = mcp_server.call_tool(
            "job.status",
            {"job_id": evaluation_job_id},
        )
        _assert_tool_ok(job_status)

        experiment = mcp_server.call_tool(
            "experiment.create",
            {
                **_write_envelope(
                    request_id="request-write-experiment",
                    correlation_id="corr-write",
                    idempotency_key="idem-write-experiment",
                ),
                "name": "smoke-experiment",
                "description": "Smoke-test controlled experiment creation.",
            },
        )
        _assert_tool_ok(experiment)

        cancelled = mcp_server.call_tool(
            "job.cancel",
            {
                **_write_envelope(
                    request_id="request-write-cancel",
                    correlation_id="corr-write",
                    idempotency_key="idem-write-cancel",
                ),
                "job_id": evaluation_job_id,
            },
        )
        _assert_tool_ok(cancelled)

        audit_lookup = mcp_server.call_tool(
            "mcp_audit.find_by_correlation",
            {"correlation_id": "corr-write"},
        )
        _assert_tool_ok(audit_lookup)

        print(f"audit_db={database_path}")
        print()
        print("[evaluation.submit_async]")
        print(f"status={evaluation.status}")
        print(f"job_id={evaluation_job_id}")
        print(f"job_status={evaluation.data['status']}")
        print()
        print("[job.status]")
        print(f"status={job_status.status}")
        print(f"job_status={job_status.data['status']}")
        print()
        print("[experiment.create]")
        print(f"status={experiment.status}")
        print(f"job_id={experiment.data['job_id']}")
        print(f"job_status={experiment.data['status']}")
        print()
        print("[job.cancel]")
        print(f"status={cancelled.status}")
        print(f"job_status={cancelled.data['status']}")
        print()
        print("[mcp_audit.find_by_correlation]")
        records = audit_lookup.data["records"]
        print(f"records={len(records)}")
        print(f"tools={[record['tool_name'] for record in records]}")
        print(f"statuses={[record['status'] for record in records]}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test MCP controlled writes, REST jobs, and audit reads."
        ),
    )
    parser.add_argument(
        "--audit-db",
        type=Path,
        default=None,
        help=(
            "Optional SQLite audit DB path. If omitted, a temporary DB is used."
        ),
    )
    return parser.parse_args()


@contextmanager
def _audit_database_path(
    audit_db: Path | None,
) -> Iterator[Path]:
    if audit_db is not None:
        audit_db.parent.mkdir(parents=True, exist_ok=True)
        yield audit_db
        return

    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "mcp-write-smoke.db"


def _write_envelope(
    *,
    request_id: str,
    correlation_id: str,
    idempotency_key: str,
) -> dict[str, object]:
    return {
        "request_id": request_id,
        "correlation_id": correlation_id,
        "idempotency_key": idempotency_key,
        "requested_by": "agent-live",
        "actor_type": "AGENT",
        "reason": "Smoke-test controlled MCP write flow",
        "metadata": {"ticket": "KAV-SMOKE"},
    }


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


if __name__ == "__main__":
    main()
