"""Published-package smoke coverage for the execution replay resolver."""

from bhanuj_governance_plugin_api import (
    EvidenceResolutionPlan,
    ExecutionReplayCapability,
    ExecutionReplayResolver,
    ReplayEvidenceBinding,
    ReplayResolutionCompletion,
    ReplayResolutionOutcome,
    ReplayToolCall,
    ReplayToolCallKind,
    ToolArgumentDigest,
    ToolArgumentDigestAlgorithm,
)


def test_public_resolver_resolves_a_declared_call_without_oss_imports() -> None:
    digest = ToolArgumentDigest(
        ToolArgumentDigestAlgorithm.HMAC_SHA256_JSON_V1,
        "sha256:" + "d" * 64,
        key_version="key-1",
    )
    capability = ExecutionReplayCapability(
        supported_tool_boundaries=("framework.tool-node",),
        unsupported_execution_surfaces=(),
        argument_digest_algorithms=(ToolArgumentDigestAlgorithm.HMAC_SHA256_JSON_V1,),
        max_trace_size=8,
        supports_async_tools=True,
        supports_subgraphs=True,
        supports_retries=True,
        supports_concurrent_execution=True,
        evidence_only=True,
        no_original_tool_fallback=True,
    )
    planned = ReplayToolCall(
        call_id="call-1",
        kind=ReplayToolCallKind.PLANNED,
        scope_id="graph.root",
        tool_symbol="tools.lookup",
        tool_schema_version="v1",
        argument_digest=digest,
        occurrence=1,
        evidence_reference="private://historical/call-1",
        response_digest="sha256:" + "b" * 64,
    )
    plan = EvidenceResolutionPlan(
        organization_id="org-a",
        project_id="project-a",
        source_execution_id="execution-1",
        replay_manifest_hash="a" * 64,
        capability=capability,
        planned_calls=(planned,),
        evidence_bindings=(
            ReplayEvidenceBinding(
                planned.call_id,
                planned.evidence_reference or "",
                planned.response_digest or "",
            ),
        ),
    )
    attempted = ReplayToolCall(
        call_id="attempt-1",
        kind=ReplayToolCallKind.ATTEMPTED,
        scope_id=planned.scope_id,
        tool_symbol=planned.tool_symbol,
        tool_schema_version=planned.tool_schema_version,
        argument_digest=planned.argument_digest,
        occurrence=planned.occurrence,
    )

    resolver = ExecutionReplayResolver(plan)
    resolution = resolver.resolve(attempted)

    assert resolution.outcome is ReplayResolutionOutcome.RESOLVED_RECORDED
    assert resolution.planned_call_id == planned.call_id
    assert resolution.selected_evidence_reference == planned.evidence_reference
    assert resolution.selected_response_digest == planned.response_digest
    assert resolver.finalize().completion is ReplayResolutionCompletion.COMPLETE
