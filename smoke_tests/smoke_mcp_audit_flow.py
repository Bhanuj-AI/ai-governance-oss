from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import get_mcp_audit_log
from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.mcp.clients import RestClient, RestClientError
from ai_governance.mcp.dto import WriteEnvelope
from ai_governance.mcp.server import create_server


def main() -> None:
    args = _parse_args()

    with _audit_database_path(args.audit_db) as database_path:
        audit_log = MCPExecutionAuditLog.sqlite(database_path)
        completed_id, stale_id = _seed_audit_records(audit_log)

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

        # Exercise a write tool in dry-run mode to verify writes create audit rows.
        write_result = mcp_server.call_tool(
            "experiment.create",
            {
                "request_id": "request-live-write",
                "correlation_id": "corr-live-write",
                "idempotency_key": "idem-live-write",
                "requested_by": "agent-live",
                "actor_type": "AGENT",
                "reason": "Smoke-test write audit creation",
                "dry_run": True,
                "metadata": {"ticket": "KAV-SMOKE"},
                "name": "smoke-test-experiment",
                "description": "Seeded dry-run experiment creation.",
            },
        )

        checks = [
            _rest_list_by_actor(client),
            _rest_get_by_audit_id(client, completed_id),
            _rest_find_by_request(client),
            _rest_find_by_correlation(client),
            _rest_get_interrupted(client, stale_id),
            _mcp_find_by_request(mcp_server),
            _mcp_get_dry_run_audit(mcp_server),
        ]

        print(f"audit_db={database_path}")
        print(f"write_tool_status={write_result.status}")
        print()
        for check in checks:
            check.print_summary()


@dataclass(frozen=True)
class SmokeCheck:
    label: str
    status: str
    payload: dict[str, Any]

    def print_summary(self) -> None:
        print(f"[{self.label}] status={self.status}")
        if self.label == "REST list by actor":
            records = self.payload["records"]
            print(f"records={len(records)}")
            print(f"statuses={[record['status'] for record in records]}")
        elif self.label == "REST get by audit_id":
            print(f"audit_id={self.payload['audit_id']}")
            print(f"status={self.payload['status']}")
            print(f"job_id={self.payload['job_id']}")
            print(
                "provider_config_summary="
                f"{self.payload['request_summary']['provider_config']}"
            )
        elif self.label == "REST stale STARTED interrupted flag":
            print(f"status={self.payload['status']}")
            print(f"interrupted={self.payload['interrupted']}")
            print(f"interrupted_reason={self.payload['interrupted_reason']}")
        elif self.label.startswith("REST find"):
            records = self.payload["records"]
            print(f"records={len(records)}")
            print(f"audit_ids={[record['audit_id'] for record in records]}")
        elif self.label == "MCP mcp_audit.get dry-run audit":
            print(f"tool_status={self.payload['status']}")
            print(f"dry_run={self.payload['dry_run']}")
        else:
            records = self.payload["records"]
            print(f"tool_records={len(records)}")
            print(f"tool_status={records[0]['status']}")
        print()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seed MCP audit data and smoke-test REST and MCP audit read flows."
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
        yield Path(tmpdir) / "mcp-audit-smoke.db"


def _seed_audit_records(
    audit_log: MCPExecutionAuditLog,
) -> tuple[str, str]:
    completed = audit_log.start(
        tool_name="evaluation.submit_async",
        operation_type="SUBMIT_EVALUATION_JOB",
        resource_type="evaluation",
        resource_id="execution-live-1",
        envelope=WriteEnvelope(
            request_id="request-live-1",
            correlation_id="corr-live-1",
            idempotency_key="idem-live-1",
            requested_by="agent-live",
            actor_type="AGENT",
            reason="Smoke-test audit reads",
            metadata={"ticket": "KAV-SMOKE"},
        ),
        payload={
            "execution_id": "execution-live-1",
            "provider_config": {"api_key": "should-not-leak"},
        },
        resolved_versions={"provider_name": "mock"},
    )
    audit_log.complete(
        completed,
        status="SUCCEEDED",
        job_id="job-live-1",
        result_reference="job:job-live-1",
    )

    stale = audit_log.start(
        tool_name="job.cancel",
        operation_type="CANCEL_JOB",
        resource_type="job",
        resource_id="job-live-2",
        envelope=WriteEnvelope(
            request_id="request-live-2",
            correlation_id="corr-live-2",
            idempotency_key="idem-live-2",
            requested_by="agent-live",
            actor_type="AGENT",
            reason="Smoke-test stale started reads",
        ),
        payload={"job_id": "job-live-2"},
    )
    audit_log._store.save(  # type: ignore[attr-defined]
        replace(
            stale,
            started_at=datetime.now(UTC) - timedelta(seconds=120),
        )
    )
    return completed.audit_id, stale.audit_id


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


def _rest_list_by_actor(
    client: TestClient,
) -> SmokeCheck:
    response = client.get(
        "/api/v1/mcp/audit",
        params={"actor_id": "agent-live"},
    )
    _assert_status(response.status_code, 200, response.json())
    return SmokeCheck(
        label="REST list by actor",
        status=str(response.status_code),
        payload=response.json(),
    )


def _rest_get_by_audit_id(
    client: TestClient,
    audit_id: str,
) -> SmokeCheck:
    response = client.get(f"/api/v1/mcp/audit/{audit_id}")
    payload = response.json()
    _assert_status(response.status_code, 200, payload)
    assert payload["status"] == "SUCCEEDED"
    assert payload["request_summary"]["provider_config"] == "<redacted>"
    return SmokeCheck(
        label="REST get by audit_id",
        status=str(response.status_code),
        payload=payload,
    )


def _rest_find_by_request(
    client: TestClient,
) -> SmokeCheck:
    response = client.get("/api/v1/mcp/audit/by-request/request-live-1")
    payload = response.json()
    _assert_status(response.status_code, 200, payload)
    assert len(payload["records"]) == 1
    return SmokeCheck(
        label="REST find by request",
        status=str(response.status_code),
        payload=payload,
    )


def _rest_find_by_correlation(
    client: TestClient,
) -> SmokeCheck:
    response = client.get("/api/v1/mcp/audit/by-correlation/corr-live-1")
    payload = response.json()
    _assert_status(response.status_code, 200, payload)
    assert len(payload["records"]) == 1
    return SmokeCheck(
        label="REST find by correlation",
        status=str(response.status_code),
        payload=payload,
    )


def _rest_get_interrupted(
    client: TestClient,
    audit_id: str,
) -> SmokeCheck:
    response = client.get(
        f"/api/v1/mcp/audit/{audit_id}",
        params={"interrupted_after_seconds": 60},
    )
    payload = response.json()
    _assert_status(response.status_code, 200, payload)
    assert payload["status"] == "STARTED"
    assert payload["interrupted"] is True
    return SmokeCheck(
        label="REST stale STARTED interrupted flag",
        status=str(response.status_code),
        payload=payload,
    )


def _mcp_find_by_request(
    mcp_server,
) -> SmokeCheck:
    result = mcp_server.call_tool(
        "mcp_audit.find_by_request",
        {"request_id": "request-live-1"},
    )
    assert result.status == "ok"
    return SmokeCheck(
        label="MCP mcp_audit.find_by_request",
        status=result.status,
        payload=result.data,
    )


def _mcp_get_dry_run_audit(
    mcp_server,
) -> SmokeCheck:
    result = mcp_server.call_tool(
        "mcp_audit.find_by_request",
        {"request_id": "request-live-write"},
    )
    assert result.status == "ok"
    records = result.data["records"]
    assert len(records) == 1
    assert records[0]["status"] == "DRY_RUN"
    return SmokeCheck(
        label="MCP mcp_audit.get dry-run audit",
        status=result.status,
        payload=records[0],
    )


def _assert_status(
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
