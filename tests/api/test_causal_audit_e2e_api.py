"""End-to-end causal-audit proof: REST submission → worker → REST detail."""

from __future__ import annotations

from typing import ClassVar
from uuid import uuid4

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies.agent_execution import get_agent_execution_service
from ai_governance.api.dependencies.causal_audit import get_causal_audit_service
from ai_governance.api.dependencies.evidence_intervention_policy import (
    get_evidence_intervention_policy_service,
    get_evidence_intervention_runtime,
)
from ai_governance.api.dependencies.replay import get_replay_source_resolver
from ai_governance.api.dependencies.repositories import (
    get_agent_execution_repository,
    get_causal_audit_repository,
    get_job_repository,
    get_replay_repository,
)
from ai_governance.api.dependencies.runtime_finding_repo import (
    get_runtime_finding_repository,
)
from ai_governance.domain.jobs import JobType
from ai_governance.services.agent_runtime_controlled_replay import (
    DeterministicAgentRuntimeReplayAdapter,
)
from ai_governance.services.causal_audit_service import CausalAuditJobHandler
from ai_governance.services.job_api_service import JobApiService
from ai_governance.services.job_executor import JobExecutor
from ai_governance.services.replay_execution import (
    ReplayExecutionAdapterRegistry,
    ReplayJobHandler,
)
from ai_governance.services.synthetic_agent_runtime_replay import (
    SyntheticAgentRuntimeReplayAdapter,
    SyntheticReplayHttpResponse,
)
from ai_governance.tenancy.domain import TenantContext
from ai_governance.workers.job_worker import JobWorker
from tests.external_adapters.schema_driven_agent_runtime import (
    SchemaDrivenAgentRuntimeAdapter,
)

CONTEXT = TenantContext("org_default", "project_default", "test", "test")
RUNTIME_COUNTERFACTUAL_EVIDENCE_DIGEST = "sha256:" + ("c" * 64)


def test_causal_audit_demos_complete_through_rest_and_worker() -> None:
    class _SimulatorTransport:
        scores: ClassVar[dict[str, float]] = {
            "synthetic://replays/cwl": 0.9,
            "synthetic://replays/calibrated": 0.2,
            "synthetic://replays/lwp": 0.2,
        }

        def post(self, _endpoint, payload, _headers, _timeout):
            return SyntheticReplayHttpResponse(
                200,
                {
                    "execution_status": "COMPLETED",
                    "isolated": True,
                    "replay_reference": payload["replay_reference"],
                    "intervention": payload["intervention"],
                    "external_execution_id": payload["external_execution_id"],
                    "runtime_tool_call_id": payload["runtime_tool_call_id"],
                    "source_evidence_digest": payload["source_evidence_digest"],
                    "counterfactual_evidence_digest": RUNTIME_COUNTERFACTUAL_EVIDENCE_DIGEST,
                    "outcome_score": self.scores[payload["replay_reference"]],
                },
            )

    _clear_dependencies()
    try:
        client = TestClient(create_app())
        executions = {
            "EVIDENCE_IGNORED": _record_synthetic_execution(
                client, "cwl", [[0.9, 0.9, 0.9]]
            ),
            "EVIDENCE_ALIGNED": _record_execution(
                client,
                "calibrated",
                [[0.2, 0.2, 0.2]],
                replay_adapter_id=SyntheticAgentRuntimeReplayAdapter.name,
                runtime_type="synthetic-agent-runtime",
                replay_reference="synthetic://replays/calibrated",
                capability_metadata={
                    "endpoint": "https://synthetic.example.test/replay"
                },
            ),
            "OVER_EXTENDED": _record_execution(
                client,
                "lwp",
                [[0.2, 0.2, 0.2], [0.9, 0.9, 0.9]],
                replay_adapter_id=SyntheticAgentRuntimeReplayAdapter.name,
                runtime_type="synthetic-agent-runtime",
                replay_reference="synthetic://replays/lwp",
                capability_metadata={
                    "endpoint": "https://synthetic.example.test/replay"
                },
            ),
            "NO_TOOL_EVIDENCE": _record_synthetic_execution(client, "no-call", []),
        }
        policy = _create_policy(client)
        audit_ids = {
            expected: _submit_audit(client, execution_id, policy)
            for expected, execution_id in executions.items()
        }

        _run_causal_audit_worker(
            SyntheticAgentRuntimeReplayAdapter(
                approved_endpoint="https://synthetic.example.test/replay",
                transport=_SimulatorTransport(),
                token_provider=lambda: None,
            )
        )

        for expected, audit_id in audit_ids.items():
            response = client.get(f"/api/v1/agents-runtime/causal-audits/{audit_id}")
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "SUCCEEDED"
            assert payload["classification"] == expected
            assert payload["diagnostics"]["classification_reason"]
            for tool_result in payload["tool_call_results"]:
                assert tool_result["intervention_strategy"] == "REPLACE"
                assert "value" in tool_result["baseline_score"]
                assert "value" in tool_result["counterfactual_score"]
                assert isinstance(tool_result["influence_score"], float)
                assert len(tool_result["counterfactual_replay_ids"]) == 1
                assert len(tool_result["counterfactual_execution_ids"]) == 1

        listing = client.get("/api/v1/agents-runtime/causal-audits?limit=10")
        assert listing.status_code == 200
        assert {item["classification"] for item in listing.json()["items"]} >= set(
            audit_ids
        )
    finally:
        _clear_dependencies()


def _record_synthetic_execution(
    client: TestClient, suffix: str, counterfactual_scores: list[list[float]]
) -> str:
    return _record_execution(
        client,
        suffix,
        counterfactual_scores,
        replay_adapter_id=SyntheticAgentRuntimeReplayAdapter.name,
        runtime_type="synthetic-agent-runtime",
        replay_reference=f"synthetic://replays/{suffix}",
        capability_metadata={"endpoint": "https://synthetic.example.test/replay"},
    )


def test_external_runtime_adapter_completes_the_same_causal_audit_path() -> None:
    """An external adapter uses only the public Replay contracts and registry."""
    _clear_dependencies()
    try:
        client = TestClient(create_app())
        execution_id = _record_execution(
            client,
            "external-adapter",
            [[0.2, 0.2, 0.2]],
            replay_adapter_id=SchemaDrivenAgentRuntimeAdapter.name,
            tool_name="external.schema.lookup",
            schema_id="external-result",
        )
        policy = _create_policy(
            client,
            tool_name="external.schema.lookup",
            schema_id="external-result",
            replacement_ref="artifact://causal-e2e/external-replacement",
        )
        audit_id = _submit_audit(client, execution_id, policy)

        _run_causal_audit_worker(SchemaDrivenAgentRuntimeAdapter())

        response = client.get(f"/api/v1/agents-runtime/causal-audits/{audit_id}")
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "SUCCEEDED"
        assert result["classification"] == "EVIDENCE_ALIGNED"
        lineage = result["tool_call_results"][0]["counterfactual_lineage"]
        assert lineage[0]["replay_status"] == "EXECUTION_COMPLETED"
        assert lineage[0]["evaluator_score"]["value"] == 0.2
    finally:
        _clear_dependencies()


def test_synthetic_runtime_adapter_completes_the_causal_audit_path() -> None:
    """REST → Replay worker → external adapter → Causal Audit stays isolated."""

    class _SimulatorTransport:
        def post(self, _endpoint, payload, _headers, _timeout):
            return SyntheticReplayHttpResponse(
                200,
                {
                    "execution_status": "COMPLETED",
                    "isolated": True,
                    "replay_reference": payload["replay_reference"],
                    "intervention": payload["intervention"],
                    "external_execution_id": payload["external_execution_id"],
                    "runtime_tool_call_id": payload["runtime_tool_call_id"],
                    "source_evidence_digest": payload["source_evidence_digest"],
                    "counterfactual_evidence_digest": RUNTIME_COUNTERFACTUAL_EVIDENCE_DIGEST,
                    "outcome_score": 0.2,
                },
            )

    _clear_dependencies()
    try:
        client = TestClient(create_app())
        execution_id = _record_execution(
            client,
            "synthetic-runtime",
            [[0.9, 0.9, 0.9]],
            replay_adapter_id=SyntheticAgentRuntimeReplayAdapter.name,
            runtime_type="synthetic-agent-runtime",
            replay_reference="synthetic://replays/causal-e2e-synthetic-runtime",
            capability_metadata={"endpoint": "https://synthetic.example.test/replay"},
            tool_name="synthetic.lookup",
            schema_id="synthetic-result",
            register_evidence=False,
            evidence_content_type="application/vnd.synthetic-agent-runtime.evidence+json",
        )
        policy = _create_policy(
            client,
            tool_name="synthetic.lookup",
            schema_id="synthetic-result",
            provider_id="opaque-reference",
        )
        audit_id = _submit_audit(client, execution_id, policy)

        _run_causal_audit_worker(
            SyntheticAgentRuntimeReplayAdapter(
                approved_endpoint="https://synthetic.example.test/replay",
                transport=_SimulatorTransport(),
                token_provider=lambda: None,
            )
        )

        result = client.get(f"/api/v1/agents-runtime/causal-audits/{audit_id}")
        assert result.status_code == 200
        payload = result.json()
        assert payload["status"] == "SUCCEEDED"
        assert payload["classification"] == "EVIDENCE_ALIGNED"
        lineage = payload["tool_call_results"][0]["counterfactual_lineage"]
        assert lineage[0]["replay_status"] == "EXECUTION_COMPLETED"
        assert lineage[0]["evaluator_score"]["value"] == 0.2
        assert (
            lineage[0]["counterfactual_evidence_digest"]
            == RUNTIME_COUNTERFACTUAL_EVIDENCE_DIGEST
        )
    finally:
        _clear_dependencies()


def _record_execution(
    client: TestClient,
    suffix: str,
    counterfactual_scores: list[list[float]],
    replay_adapter_id: str = "deterministic-agent-runtime/v1",
    runtime_type: str = "deterministic",
    replay_reference: str | None = None,
    capability_metadata: dict[str, object] | None = None,
    tool_name: str = "demo.tool",
    schema_id: str = "demo-result",
    register_evidence: bool = True,
    evidence_content_type: str = "application/json",
) -> str:
    started = client.post(
        "/api/v1/agent-executions",
        json={
            "agent_id": f"demo-causal-{suffix}",
            "agent_name": f"Causal audit {suffix}",
            "agent_version": "v1",
            "external_execution_id": f"causal-e2e-{suffix}",
            "runtime_provider": "demo",
            "metadata": {
                "replay_capability": {
                    "runtime_type": runtime_type,
                    "adapter_id": replay_adapter_id,
                    "adapter_version": "1",
                    "replay_reference": replay_reference
                    or f"artifact://causal-e2e/{suffix}",
                    "supported_interventions": ["REPLACE"],
                    **(
                        {"metadata": capability_metadata} if capability_metadata else {}
                    ),
                }
            },
        },
    )
    assert started.status_code == 201
    execution_id = started.json()["execution"]["execution_id"]
    runtime = get_evidence_intervention_runtime()
    for position, scores in enumerate(counterfactual_scores):
        evidence_ref = f"artifact://causal-e2e/{suffix}/{position}"
        original = {"execution": suffix, "position": position}
        if register_evidence:
            runtime.resolver.register(evidence_ref, original, CONTEXT)
        event = client.post(
            f"/api/v1/agent-executions/{execution_id}/events",
            json={
                "event_type": "TOOL_CALL",
                "actor_id": f"demo-tool-{position}",
                "actor_type": "TOOL",
                "tool_call_context": {
                    "schema_version": "1",
                    "runtime_tool_call_id": f"{suffix}:tool:{position}",
                    "tool_call_group_id": "risk-inputs",
                    "depends_on_tool_call_ids": [],
                },
                "evidence_references": [evidence_ref],
                "attributes": {
                    "tool": tool_name,
                    "causal_replay": {
                        "evidence_descriptor": {
                            "tool_name": tool_name,
                            "evidence_ref": evidence_ref,
                            "evidence_digest": runtime.resolver.digest(original),
                            "content_type": evidence_content_type,
                            "schema_id": schema_id,
                            "schema_version": "1",
                            "replay_adapter_id": replay_adapter_id,
                            "metadata": {},
                        },
                        "counterfactual_outcomes_by_digest": {
                            runtime.resolver.digest({"counterfactual": True}): scores
                        },
                    },
                },
            },
        )
        assert event.status_code == 201
    evaluation = client.post(
        f"/api/v1/agent-executions/{execution_id}/events",
        json={
            "event_type": "EVALUATION",
            "actor_id": "demo-scorer",
            "actor_type": "EVALUATOR",
            "attributes": {"score": 0.9},
        },
    )
    assert evaluation.status_code == 201
    completed = client.post(
        f"/api/v1/agent-executions/{execution_id}/complete",
        json={"status": "SUCCEEDED"},
    )
    assert completed.status_code == 200
    return execution_id


def _create_policy(
    client: TestClient,
    *,
    tool_name: str = "demo.tool",
    schema_id: str = "demo-result",
    replacement_ref: str = "artifact://causal-e2e/replacement",
    provider_id: str = "structured-json",
) -> dict[str, object]:
    runtime = get_evidence_intervention_runtime()
    if provider_id == "structured-json":
        runtime.resolver.register(replacement_ref, {"counterfactual": True}, CONTEXT)
        strategy_configuration = {
            "json_schema": {"type": "object"},
            "replacement_references": [replacement_ref],
        }
    else:
        strategy_configuration = {
            "counterfactual_reference_namespace": "synthetic://counterfactual",
            "runtime_attests_validation": True,
        }
    response = client.post(
        "/api/v1/agents-runtime/causal-audit/intervention-policies",
        json={
            "tool_name": tool_name,
            "schema_id": schema_id,
            "schema_version": "1",
            "allowed_strategies": ["REPLACE"],
            "provider_id": provider_id,
            "provider_version": "v1",
            "strategy_configuration": strategy_configuration,
        },
    )
    assert response.status_code == 201, response.text
    policy = response.json()
    activated = client.post(
        "/api/v1/agents-runtime/causal-audit/intervention-policies/"
        f"{policy['policy_id']}/versions/{policy['version']}/activate"
    )
    assert activated.status_code == 200, activated.text
    return policy


def _submit_audit(
    client: TestClient, execution_id: str, policy: dict[str, object]
) -> str:
    response = client.post(
        "/api/v1/agents-runtime/causal-audits",
        json={
            "execution_id": execution_id,
            "evaluator_ref": "recorded-outcome/v1",
            "intervention": {
                "strategy": "REPLACE",
                "counterfactual_samples": 3,
                "intervention_policy_id": policy["policy_id"],
                "intervention_policy_version": policy["version"],
            },
        },
    )
    assert response.status_code == 202, response.text
    return response.json()["audit_id"]


def _run_causal_audit_worker(external_adapter=None) -> None:
    jobs = get_job_repository()
    replays = get_replay_repository()
    source_store = get_replay_source_resolver()
    registry = ReplayExecutionAdapterRegistry()
    registry.register(DeterministicAgentRuntimeReplayAdapter())
    if external_adapter is not None:
        registry.register(external_adapter)
    replay_handler = ReplayJobHandler(
        replays,
        source_store,
        source_store,
        registry,
        execution_id_generator=lambda: f"causal-e2e-replay-{uuid4().hex}",
    )
    worker = JobWorker(
        worker_id="causal-e2e-worker",
        repository=jobs,
        executor=JobExecutor(
            {
                JobType.CAUSAL_AUDIT: CausalAuditJobHandler(get_causal_audit_service()),
                JobType.REPLAY_EXECUTION: _ReplayCompletionHandler(
                    replay_handler, replays, JobApiService(jobs)
                ),
            }
        ),
        job_types=(JobType.CAUSAL_AUDIT, JobType.REPLAY_EXECUTION),
    )
    while worker.run_once() is not None:
        pass


class _ReplayCompletionHandler:
    """Test worker composition matching runtime completion scheduling."""

    def __init__(self, handler, replays, jobs) -> None:
        self._handler = handler
        self._replays = replays
        self._jobs = jobs

    def handle(self, job):
        outcome = self._handler.handle(job)
        if outcome.status.value != "SUCCEEDED" or job.execution_context is None:
            return outcome
        scope = job.execution_context
        replay = self._replays.get(
            str(job.input_refs["replay_id"]), scope.organization_id, scope.project_id
        )
        audit_id = replay.metadata.get("causal_audit_id") if replay else None
        if isinstance(audit_id, str):
            from ai_governance.domain.jobs import JobExecutionContext, JobSubmission

            self._jobs.submit(
                JobSubmission(
                    JobType.CAUSAL_AUDIT,
                    {"audit_id": audit_id},
                    f"causal-audit-finalize:{audit_id}:{replay.replay_id}",
                    scope.actor_id,
                    execution_context=JobExecutionContext(
                        scope.organization_id,
                        scope.project_id,
                        scope.actor_id,
                        scope.submitted_request_id,
                        scope.correlation_id,
                    ),
                )
            )
        return outcome


def _clear_dependencies() -> None:
    get_agent_execution_service.cache_clear()
    get_agent_execution_repository.cache_clear()
    get_causal_audit_service.cache_clear()
    get_causal_audit_repository.cache_clear()
    get_job_repository.cache_clear()
    get_replay_repository.cache_clear()
    get_replay_source_resolver.cache_clear()
    get_runtime_finding_repository.cache_clear()
    get_evidence_intervention_policy_service.cache_clear()
    get_evidence_intervention_runtime.cache_clear()
