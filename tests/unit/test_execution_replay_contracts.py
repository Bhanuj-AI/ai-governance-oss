"""Focused Plugin API contract coverage for Phase 2 Task 1."""

from __future__ import annotations

from dataclasses import replace

import pytest
from bhanuj_governance_plugin_api import (
    EvidenceResolutionPlan,
    ExecutionReplayCapability,
    ReplayDivergence,
    ReplayDivergenceKind,
    ReplayEvidenceBinding,
    ReplayExecutionAttestation,
    ReplayExecutionPathCoverage,
    ReplayExecutionTrace,
    ReplayResolutionOutcome,
    ReplayToolBoundaryCoverage,
    ReplayToolCall,
    ReplayToolCallKind,
    ReplayToolResolution,
    RuntimeReplaySource,
    ToolArgumentDigest,
    ToolArgumentDigestAlgorithm,
    ToolArgumentDigestConfigurationError,
    create_tool_argument_digest,
)
from bhanuj_governance_plugin_api.replay import (
    ReplayExecutionContext,
    ReplayExecutionResult,
)

from ai_governance.spi.replay import (
    ExecutionReplayCapability as CoreExecutionReplayCapability,
)

_HEX_A = "a" * 64
_HEX_B = "b" * 64
_DIGEST_A = f"sha256:{_HEX_A}"
_DIGEST_B = f"sha256:{_HEX_B}"


class _KeyProvider:
    def get_key(
        self, *, organization_id: str, project_id: str, key_version: str
    ) -> bytes | None:
        assert (organization_id, project_id, key_version) == (
            "org-a",
            "project-a",
            "key-1",
        )
        return b"tenant-private-key"


class _NotCancelled:
    is_cancelled = False


def _capability() -> ExecutionReplayCapability:
    return ExecutionReplayCapability(
        supported_tool_boundaries=("framework.tool-node",),
        unsupported_execution_surfaces=("custom.direct-http",),
        argument_digest_algorithms=(ToolArgumentDigestAlgorithm.HMAC_SHA256_JSON_V1,),
        max_trace_size=32,
        supports_async_tools=True,
        supports_subgraphs=True,
        supports_retries=True,
        supports_concurrent_execution=True,
        evidence_only=True,
        no_original_tool_fallback=True,
    )


def _argument_digest(value: str = _DIGEST_A) -> ToolArgumentDigest:
    return ToolArgumentDigest(
        ToolArgumentDigestAlgorithm.HMAC_SHA256_JSON_V1,
        value,
        key_version="key-1",
    )


def _planned_call(
    call_id: str = "call-1",
    *,
    scope_id: str = "graph.root",
    occurrence: int = 1,
    argument_digest: ToolArgumentDigest | None = None,
    dependencies: tuple[str, ...] = (),
    retry_of: str | None = None,
) -> ReplayToolCall:
    return ReplayToolCall(
        call_id=call_id,
        kind=ReplayToolCallKind.PLANNED,
        scope_id=scope_id,
        tool_symbol="tools.lookup",
        tool_schema_version="v1",
        argument_digest=argument_digest or _argument_digest(),
        occurrence=occurrence,
        dependency_call_ids=dependencies,
        retry_of_call_id=retry_of,
        evidence_reference=f"private://evidence/{call_id}",
        response_digest=_DIGEST_B,
    )


def _binding(call: ReplayToolCall) -> ReplayEvidenceBinding:
    return ReplayEvidenceBinding(
        call.call_id,
        call.evidence_reference or "",
        call.response_digest or "",
    )


def _plan(*calls: ReplayToolCall) -> EvidenceResolutionPlan:
    return EvidenceResolutionPlan(
        organization_id="org-a",
        project_id="project-a",
        source_execution_id="execution-1",
        replay_manifest_hash=_HEX_A,
        capability=_capability(),
        planned_calls=tuple(calls),
        evidence_bindings=tuple(_binding(call) for call in calls),
    )


def _attempt(call_id: str = "attempt-1") -> ReplayToolCall:
    return ReplayToolCall(
        call_id=call_id,
        kind=ReplayToolCallKind.ATTEMPTED,
        scope_id="graph.root",
        tool_symbol="tools.lookup",
        tool_schema_version="v1",
        argument_digest=_argument_digest(),
        occurrence=1,
    )


def test_plan_digest_is_deterministic_across_input_order_and_round_trips() -> None:
    first = _planned_call("call-1")
    second = _planned_call("call-2", occurrence=2, dependencies=("call-1",))

    plan = _plan(second, first)
    reordered = _plan(first, second)

    assert plan.plan_digest == reordered.plan_digest
    assert [call.call_id for call in plan.planned_calls] == ["call-1", "call-2"]
    assert EvidenceResolutionPlan.from_payload(plan.to_payload()) == plan


def test_keyed_digest_is_key_order_independent_and_requires_key_configuration() -> None:
    first = create_tool_argument_digest(
        {"a": 1, "b": ["x", True]},
        algorithm=ToolArgumentDigestAlgorithm.HMAC_SHA256_JSON_V1,
        organization_id="org-a",
        project_id="project-a",
        key_version="key-1",
        key_provider=_KeyProvider(),
    )
    reordered = create_tool_argument_digest(
        {"b": ["x", True], "a": 1},
        algorithm=ToolArgumentDigestAlgorithm.HMAC_SHA256_JSON_V1,
        organization_id="org-a",
        project_id="project-a",
        key_version="key-1",
        key_provider=_KeyProvider(),
    )

    assert first == reordered
    with pytest.raises(ToolArgumentDigestConfigurationError, match="key provider"):
        create_tool_argument_digest(
            {"a": 1},
            algorithm=ToolArgumentDigestAlgorithm.HMAC_SHA256_JSON_V1,
            organization_id="org-a",
            project_id="project-a",
            key_version="key-1",
        )
    with pytest.raises(ValueError, match="JSON-canonicalizable"):
        create_tool_argument_digest(
            {"unsupported": object()},
            algorithm=ToolArgumentDigestAlgorithm.SHA256_JSON_V1,
        )


def test_canonical_identity_distinguishes_arguments_occurrences_and_nested_scopes() -> (
    None
):
    base = _planned_call("call-1")
    different_arguments = _planned_call(
        "call-2", occurrence=2, argument_digest=_argument_digest(_DIGEST_B)
    )
    nested = _planned_call("call-3", scope_id="graph.root.subgraph-1")

    assert base.identity_key != different_arguments.identity_key
    assert base.identity_key != nested.identity_key
    assert (
        _plan(base, different_arguments, nested).planned_calls[2].scope_id
        == "graph.root.subgraph-1"
    )


def test_repeated_and_retry_calls_are_explicit_and_validated() -> None:
    original = _planned_call("call-1")
    retry = _planned_call("call-2", occurrence=2, retry_of="call-1")

    plan = _plan(original, retry)

    assert plan.planned_calls[1].retry_of_call_id == "call-1"
    invalid_retry = replace(
        retry,
        argument_digest=_argument_digest(_DIGEST_B),
    )
    with pytest.raises(ValueError, match="retry must retain"):
        _plan(original, invalid_retry)


def test_plan_rejects_duplicate_unknown_and_cyclic_dependencies() -> None:
    first = _planned_call("call-1")
    duplicate = _planned_call("call-1", occurrence=2)
    with pytest.raises(ValueError, match="identities must be unique"):
        _plan(first, duplicate)

    unknown = _planned_call("call-2", occurrence=2, dependencies=("missing",))
    with pytest.raises(ValueError, match="unknown call"):
        _plan(first, unknown)

    cyclic_first = _planned_call("call-1", dependencies=("call-2",))
    cyclic_second = _planned_call("call-2", occurrence=2, dependencies=("call-1",))
    with pytest.raises(ValueError, match="contains a cycle"):
        _plan(cyclic_first, cyclic_second)
    with pytest.raises(ValueError, match="occurrence must be positive"):
        _planned_call("call-3", occurrence=0)
    with pytest.raises(ValueError, match="must match the declared capability"):
        _plan(
            _planned_call(
                "call-4",
                argument_digest=ToolArgumentDigest(
                    ToolArgumentDigestAlgorithm.SHA256_JSON_V1,
                    _DIGEST_A,
                ),
            )
        )


def test_trace_and_attestation_round_trip_without_private_payloads() -> None:
    attempt = _attempt()
    resolution = ReplayToolResolution(
        attempted_call_id=attempt.call_id,
        outcome=ReplayResolutionOutcome.RESOLVED_RECORDED,
        reason_code="EXACT_MATCH",
        planned_call_id="call-1",
        selected_evidence_reference="private://evidence/call-1",
        selected_response_digest=_DIGEST_B,
    )
    trace = ReplayExecutionTrace(
        attempted_calls=(attempt,), resolutions=(resolution,), complete=True
    )
    coverage = ReplayToolBoundaryCoverage(
        declared_tool_boundaries=("framework.tool-node",),
        exercised_tool_boundaries=("framework.tool-node",),
        unsupported_execution_surfaces=(),
        execution_path_coverage=ReplayExecutionPathCoverage.COMPLETE_DECLARED_BOUNDARIES,
    )
    attestation = ReplayExecutionAttestation(
        replay_manifest_hash=_HEX_A,
        resolution_plan_digest=_HEX_B,
        intervention_digest=_DIGEST_A,
        phase1_safety_schema_version="evidence-only-replay-safety/v1",
        phase1_safety_digest=_DIGEST_A,
        execution_trace_digest=trace.trace_digest,
        tool_boundary_coverage=coverage,
        complete=True,
        resolved_call_count=1,
        unresolved_call_count=0,
        blocking_divergence_count=0,
        non_blocking_divergence_count=0,
    )

    assert ReplayExecutionTrace.from_payload(trace.to_payload()) == trace
    assert (
        ReplayExecutionAttestation.from_payload(attestation.to_payload()) == attestation
    )


def test_divergence_is_typed_and_rejects_sensitive_payloads() -> None:
    divergence = ReplayDivergence(
        code="ARGUMENT_MISMATCH",
        kind=ReplayDivergenceKind.TOOL_CALL,
        blocking=True,
        attempted_call_id="attempt-1",
        safe_diagnostics={"expected_occurrence": 2},
    )
    resolution = ReplayToolResolution(
        attempted_call_id="attempt-1",
        outcome=ReplayResolutionOutcome.DIVERGED,
        reason_code="ARGUMENT_MISMATCH",
        divergence=divergence,
    )

    assert resolution.divergence == divergence
    with pytest.raises(ValueError, match="sensitive"):
        ReplayDivergence(
            code="UNSAFE",
            kind=ReplayDivergenceKind.TOOL_FREE_BRANCH,
            blocking=False,
            scope_id="graph.root",
            safe_diagnostics={"prompt": "private value"},
        )
    with pytest.raises(ValueError, match="unsupported shape"):
        ReplayToolCall.from_payload({**_planned_call().to_payload(), "response": "raw"})


def test_contract_versions_bounds_and_trace_completeness_fail_closed() -> None:
    with pytest.raises(ValueError, match="Unsupported execution replay"):
        ExecutionReplayCapability.from_payload(
            {
                **_capability().to_payload(),
                "schema_version": "execution-replay-capability/v2",
            }
        )
    calls = tuple(
        _planned_call(f"call-{index}", occurrence=index) for index in range(1, 258)
    )
    with pytest.raises(ValueError, match="at most 256"):
        _plan(*calls)
    with pytest.raises(ValueError, match="at most 1024"):
        ReplayExecutionTrace(
            attempted_calls=tuple(
                _attempt(f"attempt-{index}") for index in range(1, 1_026)
            ),
            resolutions=(),
        )
    with pytest.raises(ValueError, match="one resolution"):
        ReplayExecutionTrace(
            attempted_calls=(_attempt(),), resolutions=(), complete=True
        )
    with pytest.raises(ValueError, match="unknown attempted call"):
        ReplayExecutionTrace(
            attempted_calls=(
                replace(_attempt(), dependency_call_ids=("missing-attempt",)),
            ),
            resolutions=(),
        )
    with pytest.raises(ValueError, match="complete attestation"):
        ReplayExecutionAttestation(
            replay_manifest_hash=_HEX_A,
            resolution_plan_digest=_HEX_B,
            phase1_safety_schema_version="evidence-only-replay-safety/v1",
            phase1_safety_digest=_DIGEST_A,
            execution_trace_digest=_HEX_A,
            tool_boundary_coverage=ReplayToolBoundaryCoverage(
                declared_tool_boundaries=("framework.tool-node",),
                exercised_tool_boundaries=("framework.tool-node",),
                unsupported_execution_surfaces=(),
                execution_path_coverage=ReplayExecutionPathCoverage.COMPLETE_DECLARED_BOUNDARIES,
            ),
            complete=True,
            resolved_call_count=1,
            unresolved_call_count=1,
            blocking_divergence_count=0,
            non_blocking_divergence_count=0,
        )
    with pytest.raises(ValueError, match="Phase 1 replay-safety"):
        ReplayExecutionAttestation(
            replay_manifest_hash=_HEX_A,
            resolution_plan_digest=_HEX_B,
            phase1_safety_schema_version="evidence-only-replay-safety/v2",
            phase1_safety_digest=_DIGEST_A,
            execution_trace_digest=_HEX_A,
            tool_boundary_coverage=ReplayToolBoundaryCoverage(
                declared_tool_boundaries=("framework.tool-node",),
                exercised_tool_boundaries=(),
                unsupported_execution_surfaces=("custom.direct-http",),
                execution_path_coverage=ReplayExecutionPathCoverage.UNSUPPORTED_SURFACE,
            ),
            complete=False,
            resolved_call_count=0,
            unresolved_call_count=1,
            blocking_divergence_count=1,
            non_blocking_divergence_count=0,
        )


def test_phase1_and_generic_plugin_contracts_remain_additive() -> None:
    source = RuntimeReplaySource(
        source_agent_execution_id="source-1",
        external_execution_id="external-1",
        runtime_type="runtime",
        adapter_id="adapter-v1",
        adapter_version="v1",
        replay_reference="runtime://source-1",
        isolation_guarantee="private-snapshot/v1",
        manifest_hash=_HEX_A,
    )
    context = ReplayExecutionContext(
        replay_id="replay-1",
        source_execution_id="source-1",
        new_execution_id="result-1",
        organization_id="org-a",
        project_id="project-a",
        actor_id="actor-1",
        request_id="request-1",
        correlation_id=None,
        attempt=1,
        cancellation_token=_NotCancelled(),
        metadata={},
        runtime_replay_source=source,
    )
    result = ReplayExecutionResult(execution_status="COMPLETED")

    assert context.execution_replay_resolution_plan is None
    assert result.execution_replay_trace is None
    assert result.execution_replay_attestation is None
    assert CoreExecutionReplayCapability is ExecutionReplayCapability
