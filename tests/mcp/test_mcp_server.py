from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kavach import __version__
from kavach.mcp.audit import MCPExecutionAuditLog
from kavach.mcp.invocation_audit import MCPInvocationAuditLog
from kavach.mcp.clients import RestClient, RestClientError
from kavach.mcp.dto import EmptyRequest
from kavach.mcp.plugins import MCPToolPluginMetadata
from kavach.mcp.server import create_server


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[
            tuple[
                str,
                str,
                dict[str, Any] | None,
                dict[str, Any] | None,
            ]
        ] = []

    def __call__(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> Any:
        self.calls.append((method, path, query, body))

        if path.endswith("/missing"):
            raise RestClientError(
                status_code=404,
                payload={
                    "error": {
                        "code": "not_found",
                        "message": "Resource was not found.",
                        "details": {"id": "missing"},
                    }
                },
            )

        return {"method": method, "path": path, "query": query, "body": body}


def _server(transport: FakeTransport, *, mcp_plugins=()):
    client = RestClient(
        base_url="http://kavach.test",
        transport=transport,
    )
    return create_server(
        client,
        audit_log=MCPExecutionAuditLog.in_memory(),
        invocation_audit_log=MCPInvocationAuditLog.in_memory(),
        mcp_plugins=mcp_plugins,
    )


def test_registers_phase_1_tools() -> None:
    server = _server(FakeTransport())

    tool_names = [tool.name for tool in server.list_tools()]

    assert tool_names == [
        "authorization.permissions",
        "context.current",
        "evaluation.get",
        "evaluation.history",
        "evaluation.latest",
        "evaluation.metrics",
        "evaluation.submit_async",
        "experiment.add_candidate",
        "experiment.candidates",
        "experiment.compare_candidates",
        "experiment.create",
        "experiment.get",
        "experiment.leaderboard",
        "experiment.list",
        "experiment.run_async",
        "experiment.runs",
        "governance.compare",
        "governance.compare_candidates",
        "governance.drift",
        "governance.explain_candidate",
        "governance.explain_drift",
        "governance.generate_drift_report",
        "governance.generate_evaluation_report",
        "governance.generate_experiment_report",
        "governance.generate_investigation_report",
        "governance.investigate_audit",
        "governance.investigate_evaluation",
        "governance.investigate_execution",
        "governance.investigate_job",
        "governance.report",
        "governance.summarize_drift",
        "governance.summarize_experiment",
        "governance_decision.evaluate",
        "governance_decision.evidence",
        "governance_decision.explain",
        "governance_decision.get",
        "governance_decision.lineage",
        "governance_decision.list",
        "job.cancel",
        "job.list",
        "job.retry",
        "job.status",
        "mcp_audit.find_by_correlation",
        "mcp_audit.find_by_request",
        "mcp_audit.get",
        "mcp_audit.list",
        "membership.add",
        "membership.list",
        "membership.update",
        "ontology_graph.downstream",
        "ontology_graph.find_paths",
        "ontology_graph.get_entity",
        "ontology_graph.get_relationship",
        "ontology_graph.get_relationships",
        "ontology_graph.neighbourhood",
        "ontology_graph.upstream",
        "organization.create",
        "organization.get",
        "organization.list",
        "organization.update",
        "project.create",
        "project.get",
        "project.list",
        "project.update",
        "provider.list",
        "registry.get_dataset",
        "registry.get_model",
        "registry.get_prompt",
        "registry.list_datasets",
        "registry.list_models",
        "registry.list_prompts",
        "replay.archive",
        "replay.cancel",
        "replay.create",
        "replay.evaluate",
        "replay.get",
        "replay.list",
        "replay.result",
        "replay.submit",
        "role_assignment.assign",
        "role_assignment.list",
        "role_assignment.remove",
        "settings.categories",
        "settings.get",
        "settings.list",
        "settings.update",
        "settings.validate",
    ]


def test_registry_tool_maps_to_rest_endpoint() -> None:
    transport = FakeTransport()
    server = _server(transport)

    result = server.call_tool(
        "registry.get_model",
        {"model_id": "model-1"},
    )

    assert result.status == "ok"
    assert result.data["path"] == "/api/v1/models/model-1"
    assert transport.calls[-1] == (
        "GET",
        "/api/v1/models/model-1",
        None,
        None,
    )


class _DiscoveredMCPPlugin:
    @property
    def metadata(self) -> MCPToolPluginMetadata:
        return MCPToolPluginMetadata("discovered-mcp-plugin", "1.0.0", ">=0")

    def register(self, context) -> None:
        context.register_tool(
            name="extension.example",
            description="A discovered MCP plugin tool.",
            request_model=EmptyRequest,
            handler=lambda _request: {"source": "plugin"},
        )


def test_mcp_plugins_are_discovered_through_the_packaging_entry_point(
    monkeypatch,
) -> None:
    class _EntryPoint:
        name = "discovered-mcp-plugin"

        @staticmethod
        def load():
            return _DiscoveredMCPPlugin

    class _EntryPoints:
        @staticmethod
        def select(*, group: str):
            assert group == "kavach.mcp.plugins"
            return (_EntryPoint(),)

    monkeypatch.setattr("kavach.mcp.plugins.entry_points", lambda: _EntryPoints())
    server = _server(FakeTransport())

    assert "extension.example" in [tool.name for tool in server.list_tools()]


def test_experiment_read_tools_map_to_rest_endpoints() -> None:
    transport = FakeTransport()
    server = _server(transport)

    candidates = server.call_tool(
        "experiment.candidates",
        {"experiment_id": "experiment-1"},
    )
    runs = server.call_tool(
        "experiment.runs",
        {"experiment_id": "experiment-1"},
    )
    comparison = server.call_tool(
        "experiment.compare_candidates",
        {
            "experiment_id": "experiment-1",
            "baseline_candidate_id": "candidate-a",
            "comparison_candidate_id": "candidate-b",
        },
    )

    assert candidates.status == runs.status == comparison.status == "ok"
    assert transport.calls[-3] == (
        "GET",
        "/api/v1/experiments/experiment-1/candidates",
        None,
        None,
    )
    assert transport.calls[-2] == (
        "GET",
        "/api/v1/experiments/experiment-1/runs",
        None,
        None,
    )
    assert transport.calls[-1] == (
        "GET",
        "/api/v1/experiments/experiment-1/comparison",
        {
            "baseline_candidate_id": "candidate-a",
            "comparison_candidate_id": "candidate-b",
        },
        None,
    )


def test_evaluation_get_alias_maps_to_evaluation_endpoint() -> None:
    transport = FakeTransport()
    server = _server(transport)

    result = server.call_tool(
        "evaluation.get",
        {"evaluation_id": "evaluation-1"},
    )

    assert result.status == "ok"
    assert transport.calls[-1] == (
        "GET",
        "/api/v1/evaluations/evaluation-1",
        None,
        None,
    )


def test_settings_tools_map_to_control_plane_endpoints() -> None:
    transport = FakeTransport()
    server = _server(transport)
    context = {"organization_id": "org_default", "project_id": "project_default"}

    listed = server.call_tool("settings.list", {"context": context, "category": "Jobs"})
    updated = server.call_tool(
        "settings.update",
        {
            "context": context,
            "key": "jobs.retry_attempts",
            "value": 5,
            "request_id": "request-settings-1",
            "idempotency_key": "settings-1",
            "reason": "Tune retries",
            "scope": "PROJECT",
            "expected_version": 0,
            "dry_run": False,
        },
    )

    assert listed.status == "ok"
    assert updated.status == "ok"
    assert transport.calls[0] == (
        "GET",
        "/api/v1/settings",
        {"category": "Jobs", "scope": "SYSTEM"},
        None,
    )
    assert transport.calls[-1] == (
        "PATCH",
        "/api/v1/settings/jobs.retry_attempts",
        None,
        {
            "value": 5,
            "reason": "Tune retries",
            "scope": "PROJECT",
            "expected_version": 0,
        },
    )


def test_omitted_mcp_dry_run_uses_scoped_runtime_setting() -> None:
    class DryRunTransport(FakeTransport):
        def __call__(self, method, path, query, body):
            self.calls.append((method, path, query, body))
            if path == "/api/v1/settings/mcp.dry_run_default":
                return {"effective_value": True}
            return {"method": method, "path": path, "query": query, "body": body}

    transport = DryRunTransport()
    server = _server(transport)
    result = server.call_tool(
        "project.create",
        {
            "context": {
                "organization_id": "org_default",
                "project_id": "project_default",
            },
            "project_id": "project-new",
            "name": "New Project",
            "slug": "new-project",
            "request_id": "request-dry-default",
            "idempotency_key": "dry-default-1",
            "reason": "Verify configured safety default",
        },
    )

    assert result.status == "ok"
    assert result.data["dry_run"] is True
    assert transport.calls[0] == (
        "GET",
        "/api/v1/settings/mcp.dry_run_default",
        {"scope": "PROJECT"},
        None,
    )
    assert {call[1] for call in transport.calls[1:]} == {
        "/api/v1/settings/mcp.idempotency_expiry",
        "/api/v1/settings/mcp.audit_required",
    }


def test_mcp_audit_and_idempotency_settings_control_writes() -> None:
    class OperationalTransport(FakeTransport):
        def __call__(self, method, path, query, body):
            self.calls.append((method, path, query, body))
            if path.endswith("mcp.audit_required"):
                return {"effective_value": False}
            if path.endswith("mcp.idempotency_expiry"):
                return {"effective_value": "24h"}
            return {"method": method, "path": path, "query": query, "body": body}

    transport = OperationalTransport()
    server = _server(transport)
    payload = {
        "context": {"organization_id": "org_default", "project_id": "project_default"},
        "project_id": "project-new",
        "name": "New Project",
        "slug": "new-project",
        "request_id": "request-1",
        "idempotency_key": "same-operation",
        "reason": "Create once",
        "dry_run": False,
    }

    first = server.call_tool("project.create", payload)
    second = server.call_tool("project.create", {**payload, "request_id": "request-2"})

    assert first.status == second.status == "ok"
    assert len([call for call in transport.calls if call[0] == "POST"]) == 1
    assert server.audit_log.all_records() == []


def test_governance_tool_posts_to_rest_endpoint() -> None:
    transport = FakeTransport()
    server = _server(transport)

    result = server.call_tool(
        "governance.compare",
        {
            "baseline_evaluation_id": "baseline",
            "candidate_evaluation_id": "candidate",
        },
    )

    assert result.status == "ok"
    assert transport.calls[-1] == (
        "POST",
        "/api/v1/governance/compare",
        None,
        {
            "baseline_evaluation_id": "baseline",
            "candidate_evaluation_id": "candidate",
        },
    )


def test_phase_3_governance_tools_map_to_rest_endpoints() -> None:
    transport = FakeTransport()
    server = _server(transport)

    experiment = server.call_tool(
        "governance.summarize_experiment",
        {"experiment_id": "experiment-1"},
    )
    candidate = server.call_tool(
        "governance.explain_candidate",
        {
            "experiment_id": "experiment-1",
            "candidate_id": "candidate-1",
        },
    )
    investigation = server.call_tool(
        "governance.investigate_execution",
        {"correlation_id": "corr-1"},
    )
    report = server.call_tool(
        "governance.generate_experiment_report",
        {"experiment_id": "experiment-1", "format": "markdown"},
    )

    assert experiment.status == "ok"
    assert candidate.status == "ok"
    assert investigation.status == "ok"
    assert report.status == "ok"
    assert transport.calls[-4] == (
        "GET",
        "/api/v1/experiments/experiment-1/insights",
        None,
        None,
    )
    assert transport.calls[-3] == (
        "GET",
        "/api/v1/experiments/experiment-1/candidates/candidate-1/insights",
        None,
        None,
    )
    assert transport.calls[-2] == (
        "GET",
        "/api/v1/investigations/by-correlation/corr-1",
        None,
        None,
    )
    assert transport.calls[-1] == (
        "GET",
        "/api/v1/reports/experiments/experiment-1",
        {"format": "markdown"},
        None,
    )


def test_governance_decision_tools_map_to_rest_endpoints() -> None:
    transport = FakeTransport()
    server = _server(transport)

    evaluated = server.call_tool(
        "governance_decision.evaluate",
        {
            "target_type": "Candidate",
            "target_id": "candidate-1",
            "decision_type": "APPROVE",
            "policy_ids": [],
            "correlation_id": "corr-1",
            "request_id": "req-1",
            "metadata": {"source": "mcp-test"},
        },
    )
    listed = server.call_tool(
        "governance_decision.list",
        {"target_type": "Candidate", "target_id": "candidate-1", "limit": 10},
    )
    evidence = server.call_tool(
        "governance_decision.evidence",
        {"decision_id": "decision-1"},
    )
    lineage = server.call_tool(
        "governance_decision.lineage",
        {"decision_id": "decision-1", "depth": 3},
    )

    assert evaluated.status == "ok"
    assert listed.status == "ok"
    assert evidence.status == "ok"
    assert lineage.status == "ok"
    assert transport.calls[-4] == (
        "POST",
        "/api/v1/decisions/evaluate",
        None,
        {
            "target_type": "Candidate",
            "target_id": "candidate-1",
            "decision_type": "APPROVE",
            "policy_ids": [],
            "correlation_id": "corr-1",
            "request_id": "req-1",
            "metadata": {"source": "mcp-test"},
        },
    )
    assert transport.calls[-3] == (
        "GET",
        "/api/v1/decisions",
        {
            "target_type": "Candidate",
            "target_id": "candidate-1",
            "status": None,
            "correlation_id": None,
            "limit": 10,
        },
        None,
    )
    assert transport.calls[-2] == (
        "GET",
        "/api/v1/decisions/decision-1/evidence",
        None,
        None,
    )
    assert transport.calls[-1] == (
        "GET",
        "/api/v1/decisions/decision-1/lineage",
        {"depth": 3},
        None,
    )


def test_job_list_maps_filters_to_query_params() -> None:
    transport = FakeTransport()
    server = _server(transport)

    result = server.call_tool(
        "job.list",
        {
            "status": "FAILED",
            "job_type": "DRIFT_ANALYSIS",
            "limit": 10,
        },
    )

    assert result.status == "ok"
    assert transport.calls[-1] == (
        "GET",
        "/api/v1/jobs",
        {
            "status": "FAILED",
            "job_type": "DRIFT_ANALYSIS",
            "limit": 10,
        },
        None,
    )


def test_mcp_audit_tools_map_to_rest_endpoints() -> None:
    transport = FakeTransport()
    server = _server(transport)

    listed = server.call_tool(
        "mcp_audit.list",
        {
            "tool_name": "evaluation.submit_async",
            "status": "STARTED",
            "actor_id": "agent-1",
            "interrupted_after_seconds": 60,
        },
    )
    get = server.call_tool(
        "mcp_audit.get",
        {
            "audit_id": "audit-1",
            "interrupted_after_seconds": 60,
        },
    )
    by_request = server.call_tool(
        "mcp_audit.find_by_request",
        {"request_id": "request-1"},
    )
    by_correlation = server.call_tool(
        "mcp_audit.find_by_correlation",
        {"correlation_id": "corr-1"},
    )

    assert listed.status == "ok"
    assert get.status == "ok"
    assert by_request.status == "ok"
    assert by_correlation.status == "ok"
    assert transport.calls[-4] == (
        "GET",
        "/api/v1/mcp/audit",
        {
            "limit": 100,
            "interrupted_after_seconds": 60,
            "tool_name": "evaluation.submit_async",
            "status": "STARTED",
            "actor_id": "agent-1",
        },
        None,
    )
    assert transport.calls[-3] == (
        "GET",
        "/api/v1/mcp/audit/audit-1",
        {"interrupted_after_seconds": 60},
        None,
    )
    assert transport.calls[-2][1] == ("/api/v1/mcp/audit/by-request/request-1")
    assert transport.calls[-1][1] == ("/api/v1/mcp/audit/by-correlation/corr-1")


def test_validation_errors_are_returned_as_tool_errors() -> None:
    server = _server(FakeTransport())

    result = server.call_tool("evaluation.history", {"execution_id": " "})

    assert result.status == "error"
    assert result.error["code"] == "validation_error"


def test_rest_errors_are_returned_as_tool_errors() -> None:
    server = _server(FakeTransport())

    result = server.call_tool("registry.get_model", {"model_id": "missing"})

    assert result.status == "error"
    assert result.error == {
        "code": "not_found",
        "message": "Resource was not found.",
        "details": {"id": "missing"},
        "status_code": 404,
    }


def test_records_metrics_for_success_and_failure() -> None:
    server = _server(FakeTransport())

    server.call_tool("provider.list")
    server.call_tool("registry.get_model", {"model_id": "missing"})

    snapshot = server.metrics.snapshot()
    assert snapshot["tool_invocations_total"] == 2
    assert snapshot["tool_failures_total"] == 1
    assert snapshot["active_requests"] == 0
    assert snapshot["rest_calls"] == 2
    assert snapshot["rest_failures"] == 1


def test_handles_json_rpc_tool_list() -> None:
    server = _server(FakeTransport())

    response = server.handle_json_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
        }
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert response["result"]["tools"][0]["name"] == "authorization.permissions"


def test_initialize_reports_package_version() -> None:
    server = _server(FakeTransport())

    response = server.handle_json_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
        }
    )

    assert response["result"]["serverInfo"]["version"] == __version__


def test_handles_json_rpc_tool_call() -> None:
    server = _server(FakeTransport())

    response = server.handle_json_rpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "provider.list",
                "arguments": {},
            },
        }
    )

    content = response["result"]["content"][0]
    payload = json.loads(content["text"])
    assert response["id"] == 2
    assert response["result"]["isError"] is False
    assert payload["tool"] == "provider.list"
    assert payload["status"] == "ok"


def test_evaluation_submit_async_maps_to_job_rest_endpoint() -> None:
    transport = FakeTransport()
    server = _server(transport)

    result = server.call_tool(
        "evaluation.submit_async",
        {
            **_write_envelope(),
            "provider_name": "mock",
            "workflow_id": "workflow-1",
            "execution_id": "execution-1",
            "execution_status": "COMPLETED",
            "input": {"question": "Q"},
            "final_state": {"answer": "A"},
        },
    )

    assert result.status == "ok"
    method, path, query, body = transport.calls[-1]
    assert method == "POST"
    assert path == "/api/v1/evaluations/jobs"
    assert query is None
    assert body["idempotency_key"] == "idem-1"
    assert body["submitted_by"] == "agent-1"
    assert body["provider_name"] == "mock"
    assert body["execution_id"] == "execution-1"


def test_experiment_create_submits_job() -> None:
    transport = FakeTransport()
    server = _server(transport)

    result = server.call_tool(
        "experiment.create",
        {
            **_write_envelope(),
            "name": "claim-validation",
            "description": "Evaluate claim workflows",
        },
    )

    assert result.status == "ok"
    method, path, _query, body = transport.calls[-1]
    assert method == "POST"
    assert path == "/api/v1/jobs"
    assert body["job_type"] == "EXPERIMENT"
    assert body["input_refs"]["operation"] == "experiment.create"
    assert body["input_refs"]["name"] == "claim-validation"


def test_experiment_run_async_maps_to_run_endpoint_with_idempotency() -> None:
    transport = FakeTransport()
    server = _server(transport)

    result = server.call_tool(
        "experiment.run_async",
        {
            **_write_envelope(),
            "experiment_id": "experiment-1",
            "metric_specs": [{"name": "answer_relevance"}],
        },
    )

    assert result.status == "ok"
    method, path, _query, body = transport.calls[-1]
    assert method == "POST"
    assert path == "/api/v1/experiments/experiment-1/run"
    assert body["idempotency_key"] == "idem-1"
    assert body["submitted_by"] == "agent-1"
    assert body["metric_specs"] == [{"name": "answer_relevance"}]


def test_job_cancel_and_retry_map_to_job_mutation_endpoints() -> None:
    transport = FakeTransport()
    server = _server(transport)

    cancel = server.call_tool(
        "job.cancel",
        {
            **_write_envelope(),
            "job_id": "job-1",
        },
    )
    retry = server.call_tool(
        "job.retry",
        {
            **_write_envelope(idempotency_key="idem-2"),
            "job_id": "job-1",
        },
    )

    assert cancel.status == "ok"
    assert retry.status == "ok"
    mutation_paths = [call[1] for call in transport.calls if call[0] == "POST"]
    assert mutation_paths[-2] == "/api/v1/jobs/job-1/cancel"
    assert mutation_paths[-1] == "/api/v1/jobs/job-1/retry"


def test_write_tool_dry_run_validates_and_does_not_call_rest() -> None:
    transport = FakeTransport()
    server = _server(transport)

    result = server.call_tool(
        "experiment.create",
        {
            **_write_envelope(dry_run=True),
            "name": "claim-validation",
            "description": "Evaluate claim workflows",
        },
    )

    assert result.status == "ok"
    assert result.data["dry_run"] is True
    assert result.data["status"] == "VALIDATED"
    assert {call[1] for call in transport.calls} == {
        "/api/v1/settings/mcp.idempotency_expiry",
        "/api/v1/settings/mcp.audit_required",
    }


def test_write_tool_records_audit_without_sensitive_payloads() -> None:
    server = _server(FakeTransport())

    server.call_tool(
        "evaluation.submit_async",
        {
            **_write_envelope(),
            "provider_name": "mock",
            "workflow_id": "workflow-1",
            "execution_id": "execution-1",
            "execution_status": "COMPLETED",
            "input": {"question": "Q"},
            "final_state": {"answer": "A"},
            "provider_config": {"api_key": "secret"},
        },
    )

    records = server.audit_log.list_records()
    assert [record.status for record in records] == ["SUCCEEDED"]
    assert records[0].request_summary["provider_config"] == "<redacted>"
    assert records[0].request_id == "request-1"
    assert records[0].idempotency_key == "idem-1"


def test_every_read_invocation_is_audited_separately_from_mutations() -> None:
    server = _server(FakeTransport())

    result = server.call_tool("provider.list")

    assert result.status == "ok"
    assert server.audit_log.all_records() == []
    [invocation] = server.invocation_audit_log.all_records()
    assert invocation.tool_name == "provider.list"
    assert invocation.status == "SUCCEEDED"
    assert invocation.response_hash is not None


def test_mcp_audit_database_path_override_is_used(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "custom-audit.db"
    monkeypatch.setenv(
        "KAVACH_MCP_AUDIT_DATABASE_PATH",
        str(database_path),
    )
    client = RestClient(
        base_url="http://kavach.test",
        transport=FakeTransport(),
    )
    server = create_server(client)

    result = server.call_tool(
        "experiment.create",
        {
            **_write_envelope(dry_run=True),
            "name": "claim-validation",
            "description": "Evaluate claim workflows",
        },
    )

    assert result.status == "ok"
    assert database_path.exists()
    records = MCPExecutionAuditLog.sqlite(database_path).list_records()
    assert len(records) == 1
    assert records[0].status == "DRY_RUN"


def test_mcp_postgres_audit_configuration_is_used(monkeypatch) -> None:
    from kavach.mcp.server import _create_audit_log, get_mcp_settings

    expected = MCPExecutionAuditLog.in_memory()
    monkeypatch.setenv("KAVACH_MCP_AUDIT_REPOSITORY", "postgres")
    monkeypatch.setenv("KAVACH_MCP_AUDIT_POSTGRES_DSN", "postgresql://audit@db/kavach")
    monkeypatch.setattr(
        MCPExecutionAuditLog,
        "postgres",
        classmethod(lambda _cls, _dsn: expected),
    )

    assert _create_audit_log(get_mcp_settings()) is expected


def _write_envelope(
    *,
    idempotency_key: str = "idem-1",
    dry_run: bool = False,
) -> dict[str, object]:
    return {
        "request_id": "request-1",
        "idempotency_key": idempotency_key,
        "requested_by": "agent-1",
        "actor_type": "AGENT",
        "reason": "Validate governance flow",
        "dry_run": dry_run,
        "metadata": {"ticket": "KAV-1"},
    }
