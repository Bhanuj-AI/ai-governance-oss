"""Tests for the optional Google ADK public-context evidence adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from examples.google_adk.governed_workflow import (
    ADKWorkflowStep,
    AIGovernanceRuntimeClient,
    governed_adk_node,
)


@dataclass
class FunctionNode:
    name: str


@dataclass
class FakeContext:
    invocation_id: str = "invocation-1"
    run_id: str = "run-1"
    node_path: str = "claims.check_policy"
    node: FunctionNode | None = None
    parent_ctx: object | None = None
    attempt_count: int = 0


class RecordingEvidence:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[tuple[str, ADKWorkflowStep]] = []
        self.fail_on = fail_on

    def workflow_step_started(self, step: ADKWorkflowStep) -> None:
        self._record("STARTED", step)

    def workflow_step_completed(self, step: ADKWorkflowStep) -> None:
        self._record("COMPLETED", step)

    def workflow_step_failed(self, step: ADKWorkflowStep) -> None:
        self._record("FAILED", step)

    def _record(self, lifecycle: str, step: ADKWorkflowStep) -> None:
        if lifecycle == self.fail_on:
            raise RuntimeError("governance unavailable")
        self.calls.append((lifecycle, step))


class RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def request(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        if kwargs["url"].endswith("/api/v1/agent-executions"):
            return {"execution": {"execution_id": "execution-1"}}
        return {"execution": {"execution_id": "execution-1"}}


class FailingTransport:
    def request(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        raise OSError("control plane unavailable")


class StartOnlyTransport:
    def request(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs["url"].endswith("/api/v1/agent-executions"):
            return {"execution": {"execution_id": "execution-1"}}
        raise OSError("control plane unavailable")


def test_node_emits_started_and_completed_with_stable_parent_evidence() -> None:
    evidence = RecordingEvidence()
    parent = FakeContext(node_path="claims.prepare", node=FunctionNode("prepare"))
    context = FakeContext(node=FunctionNode("check_policy"), parent_ctx=parent, attempt_count=2)

    @governed_adk_node(evidence)  # type: ignore[arg-type]
    def check_policy(ctx: FakeContext, claim: str) -> str:
        return f"approved:{claim}"

    assert check_policy(context, "claim-7") == "approved:claim-7"
    assert [lifecycle for lifecycle, _ in evidence.calls] == ["STARTED", "COMPLETED"]
    started = evidence.calls[0][1]
    completed = evidence.calls[1][1]
    assert started.step_id == completed.step_id
    assert started.step_name == "check_policy"
    assert started.parent_step_id is not None
    assert started.attributes == {
        "adk_node_path": "claims.check_policy",
        "adk_run_id": "run-1",
        "adk_attempt_count": 2,
    }


def test_workflow_root_context_is_not_invented_as_a_parent_step() -> None:
    evidence = RecordingEvidence()
    workflow_root = FakeContext(
        node_path="claims",
        node=object(),
    )

    @governed_adk_node(evidence)  # type: ignore[arg-type]
    def check_policy(ctx: FakeContext) -> str:
        return "approved"

    assert check_policy(
        FakeContext(node=FunctionNode("check_policy"), parent_ctx=workflow_root)
    ) == "approved"
    assert evidence.calls[0][1].parent_step_id is None


def test_node_failure_is_recorded_and_original_exception_is_reraised() -> None:
    evidence = RecordingEvidence()

    @governed_adk_node(evidence)  # type: ignore[arg-type]
    def raise_policy_error(ctx: FakeContext) -> None:
        raise ValueError("policy service rejected claim")

    with pytest.raises(ValueError, match="policy service rejected claim"):
        raise_policy_error(FakeContext())
    assert [lifecycle for lifecycle, _ in evidence.calls] == ["STARTED", "FAILED"]


def test_unavailable_evidence_never_changes_node_result_or_exception() -> None:
    evidence = RecordingEvidence(fail_on="STARTED")

    @governed_adk_node(evidence)  # type: ignore[arg-type]
    def pass_through(ctx: FakeContext, value: int) -> int:
        return value + 1

    assert pass_through(FakeContext(), 4) == 5


def test_context_without_stable_public_identifiers_emits_no_ambiguous_event() -> None:
    evidence = RecordingEvidence()

    @governed_adk_node(evidence)  # type: ignore[arg-type]
    def node(ctx: object) -> str:
        return "unchanged"

    assert node(object()) == "unchanged"
    assert evidence.calls == []


def test_async_node_uses_same_lifecycle_contract() -> None:
    evidence = RecordingEvidence()

    @governed_adk_node(evidence)  # type: ignore[arg-type]
    async def async_node(ctx: FakeContext) -> str:
        return "approved"

    assert asyncio.run(async_node(FakeContext())) == "approved"
    assert [lifecycle for lifecycle, _ in evidence.calls] == ["STARTED", "COMPLETED"]


def test_node_accepts_the_default_public_context_keyword() -> None:
    evidence = RecordingEvidence()

    @governed_adk_node(evidence)  # type: ignore[arg-type]
    def node(*, ctx: FakeContext) -> str:
        return "approved"

    assert node(ctx=FakeContext()) == "approved"
    assert [lifecycle for lifecycle, _ in evidence.calls] == ["STARTED", "COMPLETED"]


def test_client_uses_root_invocation_as_external_execution_id_and_provider_neutral_event() -> None:
    transport = RecordingTransport()
    client = AIGovernanceRuntimeClient(
        "https://governance.example/",
        {"Authorization": "Bearer redacted"},
        transport,
    )

    evidence = client.start_execution(
        agent_id="claims-agent",
        agent_name="Claims agent",
        agent_version="1.0.0",
        root_invocation_id="root-invocation-7",
    )
    step = ADKWorkflowStep("step-1", "validate", None, {"adk_node_path": "validate"})
    evidence.workflow_step_started(step)
    evidence.workflow_step_completed(step)
    evidence.complete("SUCCEEDED")

    assert transport.requests[0]["payload"] == {
        "agent_id": "claims-agent",
        "agent_name": "Claims agent",
        "agent_version": "1.0.0",
        "external_execution_id": "root-invocation-7",
        "runtime_provider": "google_adk",
        "correlation_id": "root-invocation-7",
        "metadata": {},
    }
    event_payload = transport.requests[1]["payload"]
    assert event_payload["event_type"] == "WORKFLOW_STEP"
    assert event_payload["source_kind"] == "google_adk.node"
    assert event_payload["idempotency_key"] == "step-1:STARTED"
    assert all(request["headers"] == {"Authorization": "Bearer redacted"} for request in transport.requests)


def test_execution_start_delivery_failure_is_noop_and_never_blocks_the_node() -> None:
    client = AIGovernanceRuntimeClient(
        "https://governance.example", {}, FailingTransport()
    )
    evidence = client.start_execution(
        agent_id="claims-agent",
        agent_name="Claims agent",
        agent_version="1.0.0",
        root_invocation_id="root-invocation-7",
    )

    @governed_adk_node(evidence)
    def node(ctx: FakeContext) -> str:
        return "approved"

    assert node(FakeContext()) == "approved"
    evidence.complete("SUCCEEDED")


def test_execution_completion_delivery_failure_is_noop() -> None:
    client = AIGovernanceRuntimeClient(
        "https://governance.example", {}, StartOnlyTransport()
    )
    evidence = client.start_execution(
        agent_id="claims-agent",
        agent_name="Claims agent",
        agent_version="1.0.0",
        root_invocation_id="root-invocation-7",
    )

    evidence.complete("SUCCEEDED")


def test_eight_node_insurance_flow_has_only_workflow_step_evidence() -> None:
    transport = RecordingTransport()
    client = AIGovernanceRuntimeClient("https://governance.example", {}, transport)
    evidence = client.start_execution(
        agent_id="claims-agent",
        agent_name="Claims agent",
        agent_version="1.0.0",
        root_invocation_id="insurance-invocation-1",
    )
    node_names = (
        "validate_claim",
        "load_policy",
        "check_coverage",
        "check_policy",
        "calculate_payout",
        "record_decision",
        "notify_customer",
        "complete_claim",
    )
    for index, node_name in enumerate(node_names):

        @governed_adk_node(evidence, step_name=node_name)
        def deterministic_node(ctx: FakeContext) -> str:
            return "approved"

        assert deterministic_node(
            FakeContext(run_id=f"run-{index}", node_path=f"insurance.{node_name}")
        ) == "approved"
    evidence.complete("SUCCEEDED")

    event_payloads = [
        request["payload"]
        for request in transport.requests
        if request["url"].endswith("/events")
    ]
    assert len(event_payloads) == 16
    assert [payload["lifecycle"] for payload in event_payloads] == [
        lifecycle
        for _ in node_names
        for lifecycle in ("STARTED", "COMPLETED")
    ]
    assert {payload["event_type"] for payload in event_payloads} == {"WORKFLOW_STEP"}
    assert transport.requests[-1]["payload"] == {"status": "SUCCEEDED"}
