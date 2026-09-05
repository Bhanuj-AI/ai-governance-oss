"""Deterministic demo seed for Agent Runtime — executions and findings.

Seeds a realistic, idempotent dataset covering all scenarios:
- Multiple agents across different runtime providers
- All execution statuses (RECEIVED, RUNNING, SUCCEEDED, FAILED, CANCELLED)
- Full event timelines per execution (MODEL_CALL, TOOL_CALL, ERROR, etc.)
- Runtime findings with all severities and types
- Open and resolved findings to exercise the sustained-recovery logic

This module is safe to call repeatedly — it checks for existing demo data
before inserting anything.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
)
from ai_governance.domain.agent_execution.agent_execution_event import ActorType
from ai_governance.domain.causal_audit import (
    CausalAudit,
    CausalAuditClassification,
    CausalAuditStatus,
    CounterfactualReplayLineage,
    EvidenceInterventionPolicy,
    EvidenceInterventionPolicyStatus,
    EvidenceInterventionStrategy,
    InterventionConfiguration,
    OutcomeScore,
    ToolEvidenceInfluence,
)
from ai_governance.domain.replay import ControlledEvidenceStrategy
from ai_governance.domain.runtime_findings.finding import (
    EvidenceReference,
    FindingSeverity,
    FindingStatus,
    MetricSnapshot,
    ReconciliationOutcome,
    ReconciliationRecord,
    ReconciliationWindow,
    RuntimeFinding,
)
from ai_governance.tenancy.domain import TenantContext

LOGGER = logging.getLogger("ai_governance.api")

_LOCAL_REPLAY_SOURCE_REFERENCE = "artifact://demo/fraud/replay-source-transactions"
_LOCAL_REPLAY_SOURCE_EVIDENCE = {"confidence": 0.87, "status": "flagged"}
_LOCAL_PERTURBED_EVIDENCE = {"confidence": 0.37, "status": "flagged"}

# These active, reference-only policies are intentionally local fixtures. They
# match the Synthetic Agent Runtime's bounded evidence descriptors, allowing a
# developer to run a governed Causal Audit without first authoring policies by
# hand. They contain no raw evidence and are never seeded outside local/demo.
_SYNTHETIC_RUNTIME_INTERVENTION_TOOLS = (
    "policy.lookup",
    "claim_history.lookup",
    "vehicle_damage.evaluate",
    "evidence.verify",
    "risk_model.score",
    "customer_profile.lookup",
    "device_risk.lookup",
    "velocity_check",
    "fraud_model.score",
    "applicant_profile.lookup",
    "income.verify",
    "debt_obligations.lookup",
    "credit_model.score",
)


def register_local_demo_evidence(resolver: Any) -> None:
    """Register bounded local fixture evidence in the reference resolver.

    The fixture is deliberately registered with the local runtime resolver, not
    persisted in governance state. Production adapters own their evidence
    resolution and must never depend on this helper.
    """
    resolver.register(
        _LOCAL_REPLAY_SOURCE_REFERENCE,
        _LOCAL_REPLAY_SOURCE_EVIDENCE,
        TenantContext("org_default", "project_default", "local-demo", "local-demo"),
    )


# ---------------------------------------------------------------------------
# Seed entry point
# ---------------------------------------------------------------------------


def seed_agent_runtime_data(
    execution_repo: Any,
    event_repo: Any,
    finding_repo: Any,
    causal_audit_repo: Any | None = None,
    intervention_policy_repo: Any | None = None,
    organization_id: str = "org_default",
    project_id: str | None = "project_default",
) -> dict[str, list[str]]:
    """Seed agent executions and runtime findings.

    Returns changed execution, finding, and causal-audit identifiers.
    """
    now = datetime.now(UTC)

    # Seed every record independently. This permits a retry to repair a
    # partially completed seed without overwriting existing evidence or
    # tripping a durable-store uniqueness constraint.
    execution_ids: list[str] = []
    for scenario in _EXECUTION_SCENARIOS:
        exec_id, changed = _seed_execution(
            execution_repo, event_repo, scenario, organization_id, project_id, now
        )
        if changed:
            execution_ids.append(exec_id)

    # These bounded, aggregate-compatible records are intentionally separate
    # from the presentation timeline above.  They let local Studio exercise a
    # real completed healthy reconciliation window for every built-in detector.
    for scenario in _reconciliation_evidence_scenarios(now):
        exec_id, changed = _seed_execution(
            execution_repo, event_repo, scenario, organization_id, project_id, now
        )
        if changed:
            execution_ids.append(exec_id)

    finding_ids: list[str] = []
    for scenario in _FINDING_SCENARIOS:
        finding_id, changed = _seed_finding(
            finding_repo, scenario, organization_id, project_id, now
        )
        if changed:
            finding_ids.append(finding_id)

    intervention_policy_ids = _seed_synthetic_runtime_intervention_policies(
        intervention_policy_repo, organization_id, project_id, now
    )

    causal_audit_ids: list[str] = []
    if causal_audit_repo is not None:
        for scenario in _CAUSAL_AUDIT_SCENARIOS:
            audit_id = scenario["audit_id"]
            if causal_audit_repo.get(audit_id, organization_id, project_id) is None:
                audit = CausalAudit(
                    audit_id=audit_id,
                    organization_id=organization_id,
                    project_id=project_id,
                    execution_id=scenario["execution_id"],
                    agent_id=scenario["agent_id"],
                    status=CausalAuditStatus.SUCCEEDED,
                    methodology_version="causal-audit/v1",
                    evaluator_ref="recorded-outcome/v1",
                    intervention=InterventionConfiguration(
                        EvidenceInterventionStrategy.REPLACE,
                        3,
                        intervention_policy_id="demo-policy-v1",
                        intervention_policy_version=1,
                    ),
                    request_fingerprint=f"demo-causal-audit:{audit_id}",
                    created_by="local-demo",
                    created_at=now,
                    updated_at=now,
                    started_at=now,
                    completed_at=now,
                    classification=scenario["classification"],
                    tool_call_results=tuple(
                        _demo_tool_evidence_result(item)
                        for item in scenario.get("tool_call_results", ())
                    ),
                    diagnostics={
                        "classification_reason": scenario["reason"],
                        "tool_use_analysis": _demo_tool_use_analysis(scenario),
                        "demo": True,
                    },
                )
                causal_audit_repo.save(audit)
                causal_audit_ids.append(audit_id)

    LOGGER.info(
        "Seeded %d agent executions and %d runtime findings.",
        len(execution_ids),
        len(finding_ids),
    )
    result = {
        "execution_ids": execution_ids,
        "finding_ids": finding_ids,
    }
    # Preserve the established helper contract for callers that seed only
    # execution and finding evidence. The local Studio route opts into causal
    # audit demo data and receives that extra list.
    if causal_audit_repo is not None:
        result["causal_audit_ids"] = causal_audit_ids
    if intervention_policy_repo is not None:
        result["intervention_policy_ids"] = intervention_policy_ids
    return result


def is_agent_runtime_demo_seeded(
    execution_repo: Any,
    finding_repo: Any,
    causal_audit_repo: Any | None = None,
    intervention_policy_repo: Any | None = None,
    organization_id: str = "org_default",
    project_id: str | None = "project_default",
) -> bool:
    """Return whether the full, known Agent Runtime sample is available."""
    execution_ids = (
        f"demo-exec-{scenario['external_id']}" for scenario in _EXECUTION_SCENARIOS
    )
    if any(
        execution_repo.get(execution_id, organization_id, project_id) is None
        for execution_id in execution_ids
    ):
        return False
    if execution_repo.get("demo-exec-reconcile-healthy-00", organization_id, project_id) is None:
        return False
    findings_seeded = all(
        finding_repo.get(scenario["finding_id"], organization_id, project_id)
        is not None
        for scenario in _FINDING_SCENARIOS
    )
    policies_seeded = intervention_policy_repo is None or all(
        intervention_policy_repo.get(
            _synthetic_runtime_policy_id(tool_name), 1, organization_id, project_id
        )
        is not None
        for tool_name in _SYNTHETIC_RUNTIME_INTERVENTION_TOOLS
    )
    if causal_audit_repo is None:
        return findings_seeded and policies_seeded
    return findings_seeded and policies_seeded and all(
        causal_audit_repo.get(scenario["audit_id"], organization_id, project_id)
        is not None
        for scenario in _CAUSAL_AUDIT_SCENARIOS
    )


def _seed_synthetic_runtime_intervention_policies(
    repository: Any | None,
    organization_id: str,
    project_id: str | None,
    now: datetime,
) -> list[str]:
    if repository is None:
        return []
    created_ids: list[str] = []
    for tool_name in _SYNTHETIC_RUNTIME_INTERVENTION_TOOLS:
        policy_id = _synthetic_runtime_policy_id(tool_name)
        if repository.get(policy_id, 1, organization_id, project_id) is not None:
            continue
        repository.save(
            EvidenceInterventionPolicy(
                policy_id=policy_id,
                version=1,
                organization_id=organization_id,
                project_id=project_id,
                status=EvidenceInterventionPolicyStatus.ACTIVE,
                tool_name=tool_name,
                schema_id="synthetic-insurance-evidence",
                schema_version="1",
                provider_id="opaque-reference",
                provider_version="v1",
                allowed_strategies=(ControlledEvidenceStrategy.REPLACE,),
                strategy_configuration={
                    "counterfactual_reference_namespace": "synthetic://counterfactual",
                    "runtime_attests_validation": True,
                },
                created_at=now,
                created_by="local-demo",
                activated_at=now,
                activated_by="local-demo",
            )
        )
        created_ids.append(policy_id)
    return created_ids


def _synthetic_runtime_policy_id(tool_name: str) -> str:
    return "demo-synthetic-policy-" + tool_name.replace(".", "-").replace("_", "-")


def _reconciliation_evidence_scenarios(now: datetime) -> tuple[dict[str, Any], ...]:
    """Build bounded local evidence for one completed healthy window."""
    cadence_seconds = 48 * 60 * 60
    observed_end = datetime.fromtimestamp(
        (int(now.timestamp()) // cadence_seconds) * cadence_seconds, UTC
    )
    if now < observed_end + timedelta(hours=2):
        observed_end -= timedelta(seconds=cadence_seconds)
    observed_start = observed_end - timedelta(hours=24)
    baseline_start = observed_start - timedelta(days=7)
    scenarios: list[dict[str, Any]] = []
    for index in range(30):
        for prefix, started_at, status, duration, events in (
            ("reconcile-healthy", observed_start + timedelta(minutes=index * 10 + 5), AgentExecutionStatus.SUCCEEDED, 1, [
                ("EXECUTION_STARTED", "AGENT", {"workflow": "reconciliation_demo"}),
                ("TOOL_CALL", "TOOL", {"tool": "lookup_policy", "status": "succeeded"}),
                ("GOVERNANCE_DECISION", "GOVERNANCE", {"decision_outcome": "allowed"}),
                ("EVALUATION", "EVALUATOR", {"status": "succeeded"}),
                ("EXECUTION_COMPLETED", "AGENT", {"result": "ok"}),
            ]),
            ("reconcile-baseline", baseline_start + timedelta(minutes=index * 10 + 5), AgentExecutionStatus.FAILED, 30, [
                ("EXECUTION_STARTED", "AGENT", {"workflow": "reconciliation_demo"}),
                ("TOOL_CALL", "TOOL", {"tool": "lookup_policy", "status": "failed"}),
                ("GOVERNANCE_DECISION", "GOVERNANCE", {"decision_outcome": "denied"}),
                ("EVALUATION", "EVALUATOR", {"status": "failed"}),
                ("ERROR", "SYSTEM", {"error_category": "DatabaseError"}),
                ("EXECUTION_COMPLETED", "AGENT", {"result": "failed"}),
            ]),
        ):
            scenarios.append({
                "agent_id": "claims-agent-v2", "agent_name": "Claims Processing Agent", "agent_version": "2.1.0",
                "external_id": f"{prefix}-{index:02d}", "runtime": "local-demo", "status": status,
                "started_offset_hours": (now - started_at).total_seconds() / 3600,
                "duration_minutes": duration, "events": events,
            })
    return tuple(scenarios)


# ---------------------------------------------------------------------------
# Execution scenarios — covers all statuses, agents, runtimes
# ---------------------------------------------------------------------------


def _auditable_tool_call(
    tool_name: str,
    latency_ms: int,
    evidence_reference: str,
    schema_id: str,
    schema_version: str = "1",
    evidence_value: dict[str, Any] | None = None,
    counterfactual_outcomes_by_evidence: tuple[
        tuple[dict[str, Any], tuple[float, ...]], ...
    ] = (),
) -> tuple[str, str, dict[str, Any], tuple[str, ...]]:
    """Build a descriptor-bearing demo tool-call event.

    The descriptor is intentionally metadata-only: it identifies externally
    governed evidence without placing a raw tool result in control-plane
    storage.  The policy form can therefore derive the exact tool/schema
    selector from the same contract production runtimes publish.
    """
    causal_replay: dict[str, Any] = {
        "evidence_descriptor": {
            "tool_name": tool_name,
            "evidence_ref": evidence_reference,
            "evidence_digest": _evidence_digest(evidence_value)
            if evidence_value is not None
            else f"demo-evidence:{tool_name}",
            "content_type": "application/json",
            "schema_id": schema_id,
            "schema_version": schema_version,
            "replay_adapter_id": "deterministic-agent-runtime/v1",
            "metadata": {
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "confidence": {
                            "type": "number",
                            "title": "Confidence",
                        },
                        "status": {"type": "string", "title": "Status"},
                    },
                    "additionalProperties": False,
                }
            },
        }
    }
    if counterfactual_outcomes_by_evidence:
        causal_replay["counterfactual_outcomes_by_digest"] = {
            _evidence_digest(evidence): list(scores)
            for evidence, scores in counterfactual_outcomes_by_evidence
        }
    return (
        "TOOL_CALL",
        "TOOL",
        {
            "tool": tool_name,
            "latency_ms": latency_ms,
            "causal_replay": causal_replay,
        },
        (evidence_reference,),
    )


def _evidence_digest(value: dict[str, Any]) -> str:
    return "sha256:" + sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

_CAUSAL_AUDIT_SCENARIOS = (
    {
        "audit_id": "demo-causal-audit-cwl",
        "execution_id": "demo-exec-ext-claims-001",
        "agent_id": "claims-agent-v2",
        "classification": CausalAuditClassification.EVIDENCE_IGNORED,
        "reason": "The claim-history lookup changed the evaluated outcome by 0.004, below the 0.010 material-influence threshold.",
        "tool_call_results": (
            {
                "tool_call_id": "demo-event-ext-claims-001-003",
                "tool_name": "lookup_policy",
                "position": 0,
                "baseline_score": 0.870,
                "counterfactual_score": 0.866,
                "influence_score": 0.004,
                "useful": False,
                "harmful": False,
                "post_saturation": False,
                "evidence_references": ("artifact://demo/claims/policy-lookup",),
            },
        ),
    },
    {
        "audit_id": "demo-causal-audit-lwp",
        "execution_id": "demo-exec-ext-fraud-001",
        "agent_id": "fraud-detector-v1",
        "classification": CausalAuditClassification.OVER_EXTENDED,
        "reason": "Transaction evidence materially changed the outcome, then two additional calls continued after evidence saturation.",
        "tool_call_results": (
            {
                "tool_call_id": "demo-event-ext-fraud-001-002",
                "tool_name": "query_transaction_db",
                "position": 0,
                "baseline_score": 0.870,
                "counterfactual_score": 0.270,
                "influence_score": 0.600,
                "useful": True,
                "harmful": False,
                "post_saturation": False,
                "evidence_references": ("artifact://demo/fraud/transactions",),
            },
            {
                "tool_call_id": "demo-event-ext-fraud-001-004",
                "tool_name": "lookup_history",
                "position": 1,
                "baseline_score": 0.870,
                "counterfactual_score": 0.866,
                "influence_score": 0.004,
                "useful": False,
                "harmful": False,
                "post_saturation": True,
                "evidence_references": ("artifact://demo/fraud/history",),
            },
            {
                "tool_call_id": "demo-event-ext-fraud-001-005",
                "tool_name": "verify_merchant",
                "position": 2,
                "baseline_score": 0.870,
                "counterfactual_score": 0.867,
                "influence_score": 0.003,
                "useful": False,
                "harmful": False,
                "post_saturation": True,
                "evidence_references": ("artifact://demo/fraud/merchant",),
            },
        ),
    },
    {
        "audit_id": "demo-causal-audit-calibrated",
        "execution_id": "demo-exec-ext-orch-001",
        "agent_id": "orchestrator-v2",
        "classification": CausalAuditClassification.EVIDENCE_ALIGNED,
        "reason": "Research evidence materially influenced the outcome and the agent stopped without post-saturation calls.",
        "tool_call_results": (
            {
                "tool_call_id": "demo-event-ext-orch-001-003",
                "tool_name": "invoke_sub_agent",
                "position": 0,
                "baseline_score": 0.920,
                "counterfactual_score": 0.220,
                "influence_score": 0.700,
                "useful": True,
                "harmful": False,
                "post_saturation": False,
                "evidence_references": ("artifact://demo/orchestration/research",),
            },
        ),
    },
    {
        "audit_id": "demo-causal-audit-no-call",
        "execution_id": "demo-exec-ext-claims-002",
        "agent_id": "claims-agent-v2",
        "classification": CausalAuditClassification.NO_TOOL_EVIDENCE,
        "reason": "No tool call was available for causal evidence analysis.",
    },
)


def _demo_tool_evidence_result(payload: dict[str, Any]) -> ToolEvidenceInfluence:
    intervention = InterventionConfiguration(
        EvidenceInterventionStrategy.REPLACE,
        3,
        strategy_version="demo-v1",
        seed=payload["position"] + 1,
        intervention_policy_id="demo-policy-v1",
        intervention_policy_version=1,
    )
    replay_ids = tuple(
        f"demo-replay:{payload['tool_call_id']}:{index}" for index in range(3)
    )
    execution_ids = tuple(
        f"demo-counterfactual:{payload['tool_call_id']}:{index}"
        for index in range(3)
    )
    sample_score = OutcomeScore(
        payload["counterfactual_score"], "recorded_numeric", "local-demo", "v1"
    )
    return ToolEvidenceInfluence(
        tool_call_id=payload["tool_call_id"],
        tool_name=payload["tool_name"],
        position=payload["position"],
        intervention=intervention,
        counterfactual_count=3,
        baseline_score=OutcomeScore(
            payload["baseline_score"], "recorded_numeric", "local-demo", "v1"
        ),
        counterfactual_score=sample_score,
        influence_score=payload["influence_score"],
        useful=payload["useful"],
        harmful=payload["harmful"],
        post_saturation=payload["post_saturation"],
        counterfactual_replay_ids=replay_ids,
        counterfactual_execution_ids=execution_ids,
        evidence_references=payload["evidence_references"],
        diagnostics={"counterfactual_aggregation": "mean", "demo": True},
        counterfactual_lineage=tuple(
            CounterfactualReplayLineage(
                replay_id=replay_id,
                replay_execution_id=execution_id,
                replay_status="EXECUTION_COMPLETED",
                policy_id="demo-policy-v1",
                policy_version=1,
                provider_id="structured-json",
                provider_version="demo-v1",
                original_evidence_digest=f"demo-original:{payload['tool_call_id']}",
                counterfactual_evidence_reference=(
                    f"demo-counterfactual-evidence:{payload['tool_call_id']}:{index}"
                ),
                counterfactual_evidence_digest=(
                    f"demo-counterfactual-digest:{payload['tool_call_id']}:{index}"
                ),
                intervention_digest=f"demo-intervention:{payload['tool_call_id']}:{index}",
                evaluator_score=sample_score,
            )
            for index, (replay_id, execution_id) in enumerate(
                zip(replay_ids, execution_ids, strict=True)
            )
        ),
    )


def _demo_tool_use_analysis(scenario: dict[str, Any]) -> dict[str, Any]:
    results = scenario.get("tool_call_results", ())
    post_saturation = [item for item in results if item["post_saturation"]]
    material = next((item for item in results if item["useful"]), None)
    return {
        "saturation_reached_after_tool_call_id": material["tool_call_id"]
        if post_saturation and material
        else None,
        "post_saturation_tool_call_ids": [
            item["tool_call_id"] for item in post_saturation
        ],
    }


_EXECUTION_SCENARIOS: list[dict[str, Any]] = [
    # 1. Successful agent run — claims processing agent
    {
        "agent_id": "claims-agent-v2",
        "agent_name": "Claims Processing Agent",
        "agent_version": "2.1.0",
        "external_id": "ext-claims-001",
        "runtime": "langchain",
        "status": AgentExecutionStatus.SUCCEEDED,
        "started_offset_hours": 48,
        "duration_minutes": 12,
        "events": [
            ("EXECUTION_STARTED", "AGENT", {"workflow": "claims_intake"}),
            (
                "MODEL_CALL",
                "MODEL",
                {"model": "claude-sonnet-4-20250514", "tokens": 2400},
            ),
            _auditable_tool_call(
                "lookup_policy",
                120,
                "artifact://demo/claims/policy-lookup",
                "claims-policy-result",
            ),
            (
                "GOVERNANCE_DECISION",
                "GOVERNANCE",
                {"policy": "claims-policy-v3", "outcome": "APPROVED"},
            ),
            (
                "MODEL_CALL",
                "MODEL",
                {"model": "claude-sonnet-4-20250514", "tokens": 800},
            ),
            ("EXECUTION_COMPLETED", "AGENT", {"result": "approved"}),
        ],
    },
    # 2. Failed agent run — model timeout
    {
        "agent_id": "claims-agent-v2",
        "agent_name": "Claims Processing Agent",
        "agent_version": "2.1.0",
        "external_id": "ext-claims-002",
        "runtime": "langchain",
        "status": AgentExecutionStatus.FAILED,
        "started_offset_hours": 24,
        "duration_minutes": 3,
        "events": [
            ("EXECUTION_STARTED", "AGENT", {"workflow": "claims_intake"}),
            (
                "MODEL_CALL",
                "MODEL",
                {"model": "claude-sonnet-4-20250514", "tokens": 3200},
            ),
            (
                "ERROR",
                "SYSTEM",
                {
                    "error_type": "TimeoutError",
                    "message": "Model provider timed out after 120s",
                },
            ),
            ("EXECUTION_COMPLETED", "AGENT", {"result": "failed"}),
        ],
    },
    # 3. Cancelled agent run — user abort
    {
        "agent_id": "claims-agent-v2",
        "agent_name": "Claims Processing Agent",
        "agent_version": "2.1.0",
        "external_id": "ext-claims-003",
        "runtime": "langchain",
        "status": AgentExecutionStatus.CANCELLED,
        "started_offset_hours": 12,
        "duration_minutes": 1,
        "events": [
            ("EXECUTION_STARTED", "AGENT", {"workflow": "claims_intake"}),
            (
                "MODEL_CALL",
                "MODEL",
                {"model": "claude-sonnet-4-20250514", "tokens": 1500},
            ),
            ("EXECUTION_COMPLETED", "AGENT", {"result": "cancelled"}),
        ],
    },
    # 4. Successful — fraud detection agent
    {
        "agent_id": "fraud-detector-v1",
        "agent_name": "Fraud Detection Agent",
        "agent_version": "1.4.2",
        "external_id": "ext-fraud-001",
        "runtime": "crewai",
        "status": AgentExecutionStatus.SUCCEEDED,
        "started_offset_hours": 6,
        "duration_minutes": 45,
        "events": [
            ("EXECUTION_STARTED", "AGENT", {"workflow": "fraud_scan"}),
            _auditable_tool_call(
                "query_transaction_db",
                340,
                "artifact://demo/fraud/transactions",
                "transaction-record",
            ),
            ("MODEL_CALL", "MODEL", {"model": "gpt-4o-2024-11-20", "tokens": 5600}),
            _auditable_tool_call(
                "lookup_history",
                89,
                "artifact://demo/fraud/history",
                "account-history",
            ),
            _auditable_tool_call(
                "verify_merchant",
                110,
                "artifact://demo/fraud/merchant",
                "merchant-verification",
            ),
            (
                "GOVERNANCE_DECISION",
                "GOVERNANCE",
                {"policy": "fraud-policy-v2", "outcome": "FLAGGED"},
            ),
            ("EVALUATION", "EVALUATOR", {"evaluator": "risk-scorer", "score": 0.87}),
            ("EXECUTION_COMPLETED", "AGENT", {"result": "flagged"}),
        ],
    },
    # 5. Failed — tool error cascade
    {
        "agent_id": "fraud-detector-v1",
        "agent_name": "Fraud Detection Agent",
        "agent_version": "1.4.2",
        "external_id": "ext-fraud-002",
        "runtime": "crewai",
        "status": AgentExecutionStatus.FAILED,
        "started_offset_hours": 2,
        "duration_minutes": 8,
        "events": [
            ("EXECUTION_STARTED", "AGENT", {"workflow": "fraud_scan"}),
            _auditable_tool_call(
                "query_transaction_db",
                1200,
                "artifact://demo/fraud/failed-transaction-query",
                "transaction-record",
            ),
            (
                "ERROR",
                "TOOL",
                {"error_type": "DatabaseError", "message": "Connection pool exhausted"},
            ),
            (
                "ERROR",
                "SYSTEM",
                {"error_type": "RetryExhausted", "message": "3 retries failed"},
            ),
            ("EXECUTION_COMPLETED", "AGENT", {"result": "failed"}),
        ],
    },
    # 6. Running — long-running compliance review
    {
        "agent_id": "compliance-reviewer-v3",
        "agent_name": "Compliance Review Agent",
        "agent_version": "3.0.1",
        "external_id": "ext-compliance-001",
        "runtime": "langgraph",
        "status": AgentExecutionStatus.RUNNING,
        "started_offset_hours": 0.5,
        "duration_minutes": None,
        "events": [
            ("EXECUTION_STARTED", "AGENT", {"workflow": "compliance_review"}),
            (
                "MODEL_CALL",
                "MODEL",
                {"model": "claude-opus-4-20250514", "tokens": 8000},
            ),
            _auditable_tool_call(
                "fetch_regulations",
                450,
                "artifact://demo/compliance/regulations",
                "regulation-search-result",
            ),
        ],
    },
    # 7. Received — just ingested, not yet processed
    {
        "agent_id": "doc-analyzer-v1",
        "agent_name": "Document Analyzer",
        "agent_version": "1.0.0",
        "external_id": "ext-doc-001",
        "runtime": "custom",
        "status": AgentExecutionStatus.RECEIVED,
        "started_offset_hours": 0.1,
        "duration_minutes": None,
        "events": [
            ("EXECUTION_STARTED", "AGENT", {"workflow": "doc_analysis"}),
        ],
    },
    # 8. Successful — multi-agent orchestration
    {
        "agent_id": "orchestrator-v2",
        "agent_name": "Multi-Agent Orchestrator",
        "agent_version": "2.3.0",
        "external_id": "ext-orch-001",
        "runtime": "langgraph",
        "status": AgentExecutionStatus.SUCCEEDED,
        "started_offset_hours": 72,
        "duration_minutes": 120,
        "events": [
            ("EXECUTION_STARTED", "AGENT", {"workflow": "orchestration"}),
            (
                "MODEL_CALL",
                "MODEL",
                {"model": "claude-sonnet-4-20250514", "tokens": 4000},
            ),
            _auditable_tool_call(
                "invoke_sub_agent",
                5600,
                "artifact://demo/orchestration/research",
                "research-brief",
            ),
            _auditable_tool_call(
                "invoke_sub_agent",
                3200,
                "artifact://demo/orchestration/writer",
                "draft-document",
            ),
            (
                "GOVERNANCE_DECISION",
                "GOVERNANCE",
                {"policy": "orchestrator-policy-v1", "outcome": "APPROVED"},
            ),
            (
                "EVALUATION",
                "EVALUATOR",
                {"evaluator": "quality-checker", "score": 0.92},
            ),
            ("EXECUTION_COMPLETED", "AGENT", {"result": "completed"}),
        ],
    },
    # 9. Versioned local-demo source for installations seeded before causal
    # evidence descriptors were introduced.  Existing events stay immutable;
    # this separate execution lets an upgraded local Studio exercise the
    # source-derived policy flow without rewriting historical demo evidence.
    {
        "agent_id": "fraud-detector-v1",
        "agent_name": "Fraud Detection Agent",
        "agent_version": "1.4.2",
        "external_id": "ext-fraud-policy-source-001",
        "runtime": "crewai",
        "status": AgentExecutionStatus.SUCCEEDED,
        "started_offset_hours": 5,
        "duration_minutes": 8,
        "events": [
            ("EXECUTION_STARTED", "AGENT", {"workflow": "fraud_scan"}),
            _auditable_tool_call(
                "query_transaction_db",
                310,
                "artifact://demo/fraud/policy-source-transactions",
                "transaction-record",
            ),
            ("EVALUATION", "EVALUATOR", {"evaluator": "risk-scorer", "score": 0.87}),
            ("EXECUTION_COMPLETED", "AGENT", {"result": "flagged"}),
        ],
    },
    # 10. Replay-capable local-demo source. This is a new immutable execution
    # so installations seeded before the controlled Replay fixture was added
    # retain their original evidence unchanged.
    {
        "agent_id": "fraud-detector-v1",
        "agent_name": "Fraud Detection Agent",
        "agent_version": "1.4.2",
        "external_id": "ext-fraud-replay-source-001",
        "runtime": "deterministic",
        "status": AgentExecutionStatus.SUCCEEDED,
        "started_offset_hours": 4,
        "duration_minutes": 8,
        "metadata": {
            "replay_capability": {
                "runtime_type": "deterministic",
                "adapter_id": "deterministic-agent-runtime/v1",
                "adapter_version": "1",
                "replay_reference": "artifact://demo/replays/fraud-source-001",
                "supported_interventions": ["PERTURB"],
            }
        },
        "events": [
            ("EXECUTION_STARTED", "AGENT", {"workflow": "fraud_scan"}),
            _auditable_tool_call(
                "query_transaction_db",
                315,
                _LOCAL_REPLAY_SOURCE_REFERENCE,
                "transaction-record",
                evidence_value=_LOCAL_REPLAY_SOURCE_EVIDENCE,
                counterfactual_outcomes_by_evidence=(
                    (_LOCAL_PERTURBED_EVIDENCE, (0.270, 0.270, 0.270)),
                ),
            ),
            ("EVALUATION", "EVALUATOR", {"evaluator": "risk-scorer", "score": 0.87}),
            ("EXECUTION_COMPLETED", "AGENT", {"result": "flagged"}),
        ],
    },
]


def _seed_execution(
    execution_repo: Any,
    event_repo: Any,
    scenario: dict[str, Any],
    organization_id: str,
    project_id: str | None,
    now: datetime,
) -> tuple[str, bool]:
    """Ensure one execution and its event timeline exist.

    A demo request can be interrupted between durable writes.  Existing
    execution and event identifiers are therefore checked separately so a
    retry completes only the missing records.
    """
    exec_id = f"demo-exec-{scenario['external_id']}"
    changed = False
    started_at = now - timedelta(hours=scenario["started_offset_hours"])
    completed_at: datetime | None = None
    if (
        scenario["status"]
        not in {
            AgentExecutionStatus.RUNNING,
            AgentExecutionStatus.RECEIVED,
        }
        and scenario["duration_minutes"] is not None
    ):
        completed_at = started_at + timedelta(minutes=scenario["duration_minutes"])

    if execution_repo.get(exec_id, organization_id, project_id) is None:
        execution = AgentExecution(
            execution_id=exec_id,
            organization_id=organization_id,
            project_id=project_id,
            agent_id=scenario["agent_id"],
            agent_name=scenario["agent_name"],
            agent_version=scenario["agent_version"],
            external_execution_id=scenario["external_id"],
            runtime_provider=scenario["runtime"],
            status=scenario["status"],
            started_at=started_at,
            completed_at=completed_at,
            correlation_id=f"corr-{scenario['external_id']}",
            parent_execution_id=None,
            created_at=started_at - timedelta(minutes=1),
            updated_at=completed_at or now,
            metadata={
                "demo": True,
                "scenario": scenario["external_id"],
                **scenario.get("metadata", {}),
            },
            version=0,
        )
        execution_repo.save(execution)
        changed = True

    # Seed events
    seq = 1
    for event_definition in scenario["events"]:
        event_type_str, actor_type_str, attrs, *references = event_definition
        evidence_references = tuple(references[0]) if references else ()
        event_id = f"demo-event-{scenario['external_id']}-{seq:03d}"
        event = AgentExecutionEvent(
            event_id=event_id,
            execution_id=exec_id,
            organization_id=organization_id,
            project_id=project_id,
            event_type=EventType(event_type_str),
            sequence_number=seq,
            occurred_at=started_at + timedelta(minutes=seq * 0.5),
            received_at=started_at
            + timedelta(minutes=seq * 0.5)
            + timedelta(milliseconds=50),
            correlation_id=f"corr-{scenario['external_id']}",
            causation_id=f"demo-event-{scenario['external_id']}-{max(seq - 1, 1):03d}"
            if seq > 1
            else None,
            actor_id=attrs.get("tool") or attrs.get("model") or "system",
            actor_type=ActorType(actor_type_str),
            resource_references=[],
            evidence_references=evidence_references,
            attributes=attrs,
            event_schema_version="1",
        )
        if event_repo.get_by_id(event_id, exec_id, organization_id, project_id) is None:
            event_repo.save(event)
            changed = True
        seq += 1

    return exec_id, changed


# ---------------------------------------------------------------------------
# Finding scenarios — covers all severities, types, statuses
# ---------------------------------------------------------------------------

_FINDING_SCENARIOS: list[dict[str, Any]] = [
    # 1. Critical — tool failure rate spike
    {
        "finding_id": "demo-finding-tool-critical",
        "finding_type": "TOOL_FAILURE_RATE_INCREASE",
        "subject_type": "tool",
        "subject_id": "lookup_policy",
        "severity": FindingSeverity.CRITICAL,
        "status": FindingStatus.OPEN,
        "baseline_metrics": (
            MetricSnapshot(name="failure_rate", value=0.02, sample_size=1000),
        ),
        "observed_metrics": (
            MetricSnapshot(name="failure_rate", value=0.28, sample_size=200),
        ),
        "observation_count": 200,
        "detector_id": "tool_failure_rate",
        "consecutive_normal_windows": 0,
    },
    # 2. High — agent execution failure rate
    {
        "finding_id": "demo-finding-agent-high",
        "finding_type": "AGENT_EXECUTION_FAILURE_RATE_INCREASE",
        "subject_type": "agent",
        "subject_id": "claims-agent-v2",
        "severity": FindingSeverity.HIGH,
        "status": FindingStatus.OPEN,
        "baseline_metrics": (
            MetricSnapshot(name="failure_rate", value=0.05, sample_size=500),
        ),
        "observed_metrics": (
            MetricSnapshot(name="failure_rate", value=0.18, sample_size=100),
        ),
        "observation_count": 100,
        "detector_id": "agent_execution_failure_rate",
        "consecutive_normal_windows": 0,
    },
    # 3. Medium — latency regression
    {
        "finding_id": "demo-finding-latency-medium",
        "finding_type": "EXECUTION_LATENCY_REGRESSION",
        "subject_type": "agent",
        "subject_id": "fraud-detector-v1",
        "severity": FindingSeverity.MEDIUM,
        "status": FindingStatus.OPEN,
        "baseline_metrics": (
            MetricSnapshot(name="p50_latency_ms", value=1200, sample_size=300),
        ),
        "observed_metrics": (
            MetricSnapshot(name="p50_latency_ms", value=3400, sample_size=50),
        ),
        "observation_count": 50,
        "detector_id": "execution_latency_regression",
        "consecutive_normal_windows": 0,
    },
    # 4. Low — evaluation failure rate increase
    {
        "finding_id": "demo-finding-eval-low",
        "finding_type": "EVALUATION_FAILURE_RATE_INCREASE",
        "subject_type": "evaluator",
        "subject_id": "risk-scorer",
        "severity": FindingSeverity.LOW,
        "status": FindingStatus.OPEN,
        "baseline_metrics": (
            MetricSnapshot(name="failure_rate", value=0.03, sample_size=200),
        ),
        "observed_metrics": (
            MetricSnapshot(name="failure_rate", value=0.12, sample_size=80),
        ),
        "observation_count": 80,
        "detector_id": "evaluation_failure_rate",
        "consecutive_normal_windows": 0,
    },
    # 5. Info — policy denial rate increase
    {
        "finding_id": "demo-finding-policy-info",
        "finding_type": "POLICY_DENIAL_RATE_INCREASE",
        "subject_type": "policy",
        "subject_id": "claims-policy-v3",
        "severity": FindingSeverity.INFO,
        "status": FindingStatus.OPEN,
        "baseline_metrics": (
            MetricSnapshot(name="denial_rate", value=0.05, sample_size=400),
        ),
        "observed_metrics": (
            MetricSnapshot(name="denial_rate", value=0.15, sample_size=100),
        ),
        "observation_count": 100,
        "detector_id": "policy_denial_rate",
        "consecutive_normal_windows": 0,
    },
    # 6. High — repeated runtime error
    {
        "finding_id": "demo-finding-error-high",
        "finding_type": "REPEATED_RUNTIME_ERROR",
        "subject_type": "error",
        "subject_id": "DatabaseError",
        "severity": FindingSeverity.HIGH,
        "status": FindingStatus.OPEN,
        "baseline_metrics": (
            MetricSnapshot(name="error_count", value=2, sample_size=100),
        ),
        "observed_metrics": (
            MetricSnapshot(name="error_count", value=15, sample_size=50),
        ),
        "observation_count": 50,
        "detector_id": "repeated_runtime_error",
        "consecutive_normal_windows": 0,
    },
    # A real operator path: one retained completed healthy window plus the
    # seeded current window lets the next Studio Reconcile resolve it.
    {
        "finding_id": "demo-finding-reconcile-ready",
        "finding_type": "TOOL_FAILURE_RATE_INCREASE",
        "subject_type": "tool",
        "subject_id": "lookup_policy",
        "severity": FindingSeverity.MEDIUM,
        "status": FindingStatus.OPEN,
        "baseline_metrics": (),
        "observed_metrics": (),
        "observation_count": 0,
        "detector_id": "tool_failure_rate",
        "consecutive_normal_windows": 0,
        "seed_prior_healthy_window": True,
    },
    # 7. Resolved — previously critical, now normal (sustained recovery)
    {
        "finding_id": "demo-finding-resolved",
        "finding_type": "TOOL_FAILURE_RATE_INCREASE",
        "subject_type": "tool",
        "subject_id": "fetch_regulations",
        "severity": FindingSeverity.MEDIUM,
        "status": FindingStatus.RESOLVED,
        "baseline_metrics": (
            MetricSnapshot(name="failure_rate", value=0.01, sample_size=800),
        ),
        "observed_metrics": (
            MetricSnapshot(name="failure_rate", value=0.03, sample_size=150),
        ),
        "observation_count": 150,
        "detector_id": "tool_failure_rate",
        "consecutive_normal_windows": 0,
    },
]


def _seed_finding(
    finding_repo: Any,
    scenario: dict[str, Any],
    organization_id: str,
    project_id: str | None,
    now: datetime,
) -> tuple[str, bool]:
    """Ensure one runtime finding exists without overwriting observations."""
    if (
        finding_repo.get(scenario["finding_id"], organization_id, project_id)
        is not None
    ):
        return scenario["finding_id"], False

    first_detected = now - timedelta(hours=24)
    healthy_windows: tuple[ReconciliationWindow, ...] = ()
    last_reconciliation: ReconciliationRecord | None = None
    if scenario.get("seed_prior_healthy_window"):
        cadence_seconds = 48 * 60 * 60
        candidate_end = datetime.fromtimestamp(
            (int(now.timestamp()) // cadence_seconds) * cadence_seconds, UTC
        )
        selected_end = candidate_end
        if now < selected_end + timedelta(hours=2):
            selected_end -= timedelta(seconds=cadence_seconds)
        previous_end = selected_end - timedelta(seconds=cadence_seconds)
        observed_start = previous_end - timedelta(hours=24)
        prior_window = ReconciliationWindow(
            observed_start=observed_start,
            observed_end=previous_end,
            baseline_start=observed_start - timedelta(days=7),
            baseline_end=observed_start,
        )
        healthy_windows = (prior_window,)
        last_reconciliation = ReconciliationRecord(
            window=prior_window,
            outcome=ReconciliationOutcome.HEALTHY_AWAITING,
            reconciled_at=previous_end,
            detail="Local demo: prior completed healthy window.",
        )

    finding = RuntimeFinding(
        finding_id=scenario["finding_id"],
        organization_id=organization_id,
        project_id=project_id,
        finding_type=scenario["finding_type"],
        subject_type=scenario["subject_type"],
        subject_id=scenario["subject_id"],
        severity=scenario["severity"],
        status=scenario["status"],
        baseline_window="7d",
        observation_window="24h",
        baseline_metrics=scenario["baseline_metrics"],
        observed_metrics=scenario["observed_metrics"],
        observation_count=scenario["observation_count"],
        evidence_references=(
            EvidenceReference(kind="detector_id", value=scenario["detector_id"]),
            EvidenceReference(kind="threshold", value="0.05"),
        ),
        related_execution_ids=(),
        detector_id=scenario["detector_id"],
        detector_version="1",
        first_detected_at=first_detected,
        last_detected_at=now,
        resolved_at=now - timedelta(hours=2)
        if scenario["status"] is FindingStatus.RESOLVED
        else None,
        created_at=first_detected,
        updated_at=now,
        consecutive_normal_windows=len(healthy_windows),
        healthy_reconciliation_windows=healthy_windows,
        last_reconciliation=last_reconciliation,
    )

    finding_repo.save(finding)
    return finding.finding_id, True
