"""Deterministic conformance tests for the Plugin API replay resolver."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from bhanuj_governance_plugin_api import (
    EvidenceResolutionPlan,
    ExecutionReplayCapability,
    ExecutionReplayResolver,
    ExecutionReplayResolverConfigurationError,
    ReplayEvidenceBinding,
    ReplayInterventionBinding,
    ReplayResolutionCompletion,
    ReplayResolutionOutcome,
    ReplayResolutionReasonCode,
    ReplayResolutionSummary,
    ReplayToolCall,
    ReplayToolCallKind,
    ToolArgumentDigest,
    ToolArgumentDigestAlgorithm,
)

from ai_governance.spi.replay import (
    ExecutionReplayResolver as CoreExecutionReplayResolver,
)

_MANIFEST = "a" * 64
_RESPONSE = f"sha256:{'b' * 64}"
_ALTERNATIVE_RESPONSE = f"sha256:{'c' * 64}"
_ARGUMENT = f"sha256:{'d' * 64}"
_DIFFERENT_ARGUMENT = f"sha256:{'e' * 64}"
_INTERVENTION = f"sha256:{'f' * 64}"


def _capability() -> ExecutionReplayCapability:
    return ExecutionReplayCapability(
        supported_tool_boundaries=("framework.tool-node",),
        unsupported_execution_surfaces=(),
        argument_digest_algorithms=(ToolArgumentDigestAlgorithm.HMAC_SHA256_JSON_V1,),
        max_trace_size=32,
        supports_async_tools=True,
        supports_subgraphs=True,
        supports_retries=True,
        supports_concurrent_execution=True,
        evidence_only=True,
        no_original_tool_fallback=True,
    )


def _digest(value: str = _ARGUMENT) -> ToolArgumentDigest:
    return ToolArgumentDigest(
        ToolArgumentDigestAlgorithm.HMAC_SHA256_JSON_V1,
        value,
        key_version="key-1",
    )


def _planned(
    call_id: str,
    *,
    tool: str = "tools.lookup",
    schema: str = "v1",
    scope: str = "graph.root",
    digest: ToolArgumentDigest | None = None,
    occurrence: int = 1,
    dependencies: tuple[str, ...] = (),
    retry_of: str | None = None,
) -> ReplayToolCall:
    return ReplayToolCall(
        call_id=call_id,
        kind=ReplayToolCallKind.PLANNED,
        scope_id=scope,
        tool_symbol=tool,
        tool_schema_version=schema,
        argument_digest=digest or _digest(),
        occurrence=occurrence,
        dependency_call_ids=dependencies,
        retry_of_call_id=retry_of,
        evidence_reference=f"private://historical/{call_id}",
        response_digest=_RESPONSE,
    )


def _attempt(
    planned: ReplayToolCall, call_id: str = "attempt-1", **changes
) -> ReplayToolCall:
    values = {
        "call_id": call_id,
        "kind": ReplayToolCallKind.ATTEMPTED,
        "scope_id": planned.scope_id,
        "tool_symbol": planned.tool_symbol,
        "tool_schema_version": planned.tool_schema_version,
        "argument_digest": planned.argument_digest,
        "occurrence": planned.occurrence,
        "dependency_call_ids": planned.dependency_call_ids,
        "retry_of_call_id": planned.retry_of_call_id,
    }
    values.update(changes)
    return ReplayToolCall(**values)


def _plan(*calls: ReplayToolCall) -> EvidenceResolutionPlan:
    return EvidenceResolutionPlan(
        organization_id="org-a",
        project_id="project-a",
        source_execution_id="execution-1",
        replay_manifest_hash=_MANIFEST,
        capability=_capability(),
        planned_calls=tuple(calls),
        evidence_bindings=tuple(
            ReplayEvidenceBinding(
                call.call_id,
                call.evidence_reference or "",
                call.response_digest or "",
            )
            for call in calls
        ),
    )


def _binding(
    plan: EvidenceResolutionPlan, target: str = "call-1"
) -> ReplayInterventionBinding:
    return ReplayInterventionBinding(
        replay_manifest_hash=plan.replay_manifest_hash,
        resolution_plan_digest=plan.plan_digest,
        target_planned_call_id=target,
        intervention_digest=_INTERVENTION,
        replacement_evidence_reference="private://counterfactual/call-1",
        replacement_response_digest=_ALTERNATIVE_RESPONSE,
    )


def test_exact_historical_call_resolves_and_finalizes_complete() -> None:
    planned = _planned("call-1")
    resolver = ExecutionReplayResolver(_plan(planned))

    resolution = resolver.resolve(_attempt(planned))
    summary = resolver.finalize()

    assert resolution.outcome is ReplayResolutionOutcome.RESOLVED_RECORDED
    assert resolution.planned_call_id == planned.call_id
    assert resolution.selected_evidence_reference == planned.evidence_reference
    assert resolution.selected_response_digest == planned.response_digest
    assert summary.completion is ReplayResolutionCompletion.COMPLETE
    assert summary.consumed_planned_call_ids == ("call-1",)
    assert ReplayResolutionSummary.from_payload(summary.to_payload()) == summary
    assert CoreExecutionReplayResolver is ExecutionReplayResolver


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"argument_digest": _digest(_DIFFERENT_ARGUMENT)}, "ARGUMENT_DIGEST_MISMATCH"),
        ({"tool_symbol": "tools.other"}, "UNOBSERVED_TOOL_CALL"),
        ({"tool_schema_version": "v2"}, "TOOL_IDENTITY_MISMATCH"),
        ({"scope_id": "graph.other"}, "TOOL_IDENTITY_MISMATCH"),
    ),
)
def test_identity_mismatches_fail_closed_with_deterministic_precedence(
    changes: dict[str, object], reason: str
) -> None:
    planned = _planned("call-1")
    resolver = ExecutionReplayResolver(_plan(planned))

    result = resolver.resolve(_attempt(planned, **changes))

    assert result.outcome is ReplayResolutionOutcome.DIVERGED
    assert result.reason_code == reason
    assert result.divergence is not None
    assert result.divergence.safe_diagnostics == {"reason": reason}
    assert resolver.finalize().completion is ReplayResolutionCompletion.FAILED


def test_attempted_call_id_cannot_bypass_an_identity_mismatch() -> None:
    planned = _planned("call-1")

    result = ExecutionReplayResolver(_plan(planned)).resolve(
        _attempt(
            planned,
            call_id=planned.call_id,
            argument_digest=_digest(_DIFFERENT_ARGUMENT),
        )
    )

    assert result.outcome is ReplayResolutionOutcome.DIVERGED
    assert result.reason_code is ReplayResolutionReasonCode.ARGUMENT_DIGEST_MISMATCH


def test_incompatible_digest_algorithm_is_invalid_not_a_weaker_match() -> None:
    planned = _planned("call-1")
    incompatible = ToolArgumentDigest(
        ToolArgumentDigestAlgorithm.SHA256_JSON_V1,
        _ARGUMENT,
    )

    result = ExecutionReplayResolver(_plan(planned)).resolve(
        _attempt(planned, argument_digest=incompatible)
    )

    assert result.outcome is ReplayResolutionOutcome.INVALID
    assert result.reason_code is ReplayResolutionReasonCode.UNSUPPORTED_DIGEST_ALGORITHM


def test_intervention_selects_only_the_approved_target_and_replacement() -> None:
    first = _planned("call-1")
    second = _planned("call-2", tool="tools.verify")
    plan = _plan(first, second)
    binding = _binding(plan, target="call-1")
    resolver = ExecutionReplayResolver(plan, binding)

    recorded = resolver.resolve(_attempt(second, "attempt-2"))
    intervention = resolver.resolve(
        _attempt(first), intervention_digest=binding.intervention_digest
    )

    assert recorded.outcome is ReplayResolutionOutcome.RESOLVED_RECORDED
    assert recorded.selected_evidence_reference == second.evidence_reference
    assert intervention.outcome is ReplayResolutionOutcome.RESOLVED_INTERVENTION
    assert (
        intervention.selected_evidence_reference
        == binding.replacement_evidence_reference
    )
    assert intervention.selected_response_digest == binding.replacement_response_digest
    assert resolver.finalize().completion is ReplayResolutionCompletion.COMPLETE


def test_intervention_digest_is_required_and_the_target_can_be_applied_once() -> None:
    planned = _planned("call-1")
    plan = _plan(planned)
    binding = _binding(plan)
    missing_digest = ExecutionReplayResolver(plan, binding)

    invalid = missing_digest.resolve(_attempt(planned))
    applied = ExecutionReplayResolver(plan, binding)
    first = applied.resolve(_attempt(planned), intervention_digest=_INTERVENTION)
    duplicate = applied.resolve(
        _attempt(planned, "attempt-2"), intervention_digest=_INTERVENTION
    )

    assert invalid.outcome is ReplayResolutionOutcome.INVALID
    assert invalid.reason_code is ReplayResolutionReasonCode.INTERVENTION_MISMATCH
    assert first.outcome is ReplayResolutionOutcome.RESOLVED_INTERVENTION
    assert duplicate.reason_code is ReplayResolutionReasonCode.DUPLICATE_TOOL_CALL
    assert applied.finalize().completion is ReplayResolutionCompletion.FAILED


def test_wrong_intervention_digest_fails_and_missing_intervention_is_incomplete() -> (
    None
):
    planned = _planned("call-1")
    plan = _plan(planned)
    binding = _binding(plan)
    resolver = ExecutionReplayResolver(plan, binding)

    wrong = resolver.resolve(_attempt(planned), intervention_digest=_RESPONSE)
    incomplete = ExecutionReplayResolver(plan, binding).finalize()

    assert wrong.outcome is ReplayResolutionOutcome.INVALID
    assert wrong.reason_code is ReplayResolutionReasonCode.INTERVENTION_MISMATCH
    assert incomplete.completion is ReplayResolutionCompletion.INCOMPLETE
    assert incomplete.intervention_required is True
    assert incomplete.intervention_applied_call_id is None


def test_invalid_intervention_configuration_fails_construction() -> None:
    planned = _planned("call-1")
    plan = _plan(planned)
    bad_manifest = replace(_binding(plan), replay_manifest_hash="b" * 64)
    bad_plan = replace(_binding(plan), resolution_plan_digest="b" * 64)
    bad_target = replace(_binding(plan), target_planned_call_id="missing-call")

    with pytest.raises(ExecutionReplayResolverConfigurationError, match="manifest"):
        ExecutionReplayResolver(plan, bad_manifest)
    with pytest.raises(
        ExecutionReplayResolverConfigurationError, match="resolution plan"
    ):
        ExecutionReplayResolver(plan, bad_plan)
    with pytest.raises(ExecutionReplayResolverConfigurationError, match="target"):
        ExecutionReplayResolver(plan, bad_target)


def test_independent_calls_are_order_independent() -> None:
    first = _planned("call-1")
    second = _planned("call-2", tool="tools.verify")
    plan = _plan(first, second)

    left = ExecutionReplayResolver(plan)
    left.resolve(_attempt(second, "attempt-2"))
    left.resolve(_attempt(first, "attempt-1"))
    right = ExecutionReplayResolver(plan)
    right.resolve(_attempt(first, "attempt-1"))
    right.resolve(_attempt(second, "attempt-2"))

    assert left.finalize() == right.finalize()
    assert left.finalize().completion is ReplayResolutionCompletion.COMPLETE


def test_dependencies_and_retries_are_exact_and_partial_ordered() -> None:
    first = _planned("call-1")
    second = _planned(
        "call-2",
        occurrence=2,
        dependencies=("call-1",),
        retry_of="call-1",
    )
    plan = _plan(first, second)
    premature = ExecutionReplayResolver(plan).resolve(_attempt(second, "attempt-2"))
    resolver = ExecutionReplayResolver(plan)

    resolver.resolve(_attempt(first, "attempt-1"))
    retry = resolver.resolve(_attempt(second, "attempt-2"))

    assert premature.reason_code is ReplayResolutionReasonCode.DEPENDENCY_VIOLATION
    assert retry.outcome is ReplayResolutionOutcome.RESOLVED_RECORDED
    assert resolver.finalize().completion is ReplayResolutionCompletion.COMPLETE


def test_unplanned_retry_and_duplicate_consumption_diverge() -> None:
    planned = _planned("call-1")
    retry = ExecutionReplayResolver(_plan(planned)).resolve(
        _attempt(planned, retry_of_call_id="call-1")
    )
    resolver = ExecutionReplayResolver(_plan(planned))
    resolver.resolve(_attempt(planned))
    duplicate = resolver.resolve(_attempt(planned, "attempt-2"))

    assert retry.reason_code is ReplayResolutionReasonCode.UNPLANNED_RETRY
    assert duplicate.reason_code is ReplayResolutionReasonCode.DUPLICATE_TOOL_CALL


def test_concurrent_attempts_cannot_consume_the_same_planned_call_twice() -> None:
    planned = _planned("call-1")
    resolver = ExecutionReplayResolver(_plan(planned))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda index: resolver.resolve(_attempt(planned, f"attempt-{index}")),
                (1, 2),
            )
        )

    assert {result.outcome for result in results} == {
        ReplayResolutionOutcome.RESOLVED_RECORDED,
        ReplayResolutionOutcome.DIVERGED,
    }
    assert resolver.finalize().consumed_planned_call_ids == ("call-1",)


def test_concurrent_independent_calls_both_resolve() -> None:
    first = _planned("call-1")
    second = _planned("call-2", tool="tools.verify")
    resolver = ExecutionReplayResolver(_plan(first, second))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda item: resolver.resolve(_attempt(*item)),
                ((first, "attempt-1"), (second, "attempt-2")),
            )
        )

    assert {result.outcome for result in results} == {
        ReplayResolutionOutcome.RESOLVED_RECORDED
    }
    assert resolver.finalize().completion is ReplayResolutionCompletion.COMPLETE


def test_sessions_do_not_share_state() -> None:
    planned = _planned("call-1")
    plan = _plan(planned)
    first = ExecutionReplayResolver(plan)
    second = ExecutionReplayResolver(plan)

    assert (
        first.resolve(_attempt(planned)).outcome
        is ReplayResolutionOutcome.RESOLVED_RECORDED
    )
    assert (
        second.resolve(_attempt(planned)).outcome
        is ReplayResolutionOutcome.RESOLVED_RECORDED
    )


def test_first_failure_is_terminal_and_diagnostics_are_bounded() -> None:
    planned = _planned("call-1")
    resolver = ExecutionReplayResolver(_plan(planned))
    first = resolver.resolve(_attempt(planned, tool_symbol="tools.unknown"))
    later = resolver.resolve(_attempt(planned, "attempt-2"))
    summary = resolver.finalize()

    assert first.divergence is not None
    assert first.divergence.safe_diagnostics == {"reason": "UNOBSERVED_TOOL_CALL"}
    assert later.reason_code is ReplayResolutionReasonCode.SESSION_TERMINAL
    assert summary.completion is ReplayResolutionCompletion.FAILED
    assert (
        summary.terminal_reason_code is ReplayResolutionReasonCode.UNOBSERVED_TOOL_CALL
    )
    assert summary.blocking_divergence_count == 1


def test_finalization_is_explicit_for_incomplete_and_tool_free_plans() -> None:
    first = _planned("call-1")
    second = _planned("call-2", tool="tools.verify")
    incomplete = ExecutionReplayResolver(_plan(first, second))
    incomplete.resolve(_attempt(first))
    empty_plan = _plan()

    assert incomplete.finalize().completion is ReplayResolutionCompletion.INCOMPLETE
    assert incomplete.finalize().remaining_planned_call_ids == ("call-2",)
    assert (
        ExecutionReplayResolver(empty_plan).finalize().completion
        is ReplayResolutionCompletion.COMPLETE
    )


def test_plan_digest_is_revalidated_before_resolution() -> None:
    plan = _plan(_planned("call-1"))
    object.__setattr__(plan, "plan_digest", "0" * 64)

    with pytest.raises(ExecutionReplayResolverConfigurationError, match="integrity"):
        ExecutionReplayResolver(plan)
