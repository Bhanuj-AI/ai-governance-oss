from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from ai_governance.decisions.enums import (
    DecisionProducerType,
    DecisionTargetType,
)
from ai_governance.decisions.evidence import (
    DecisionEvidenceGraph,
    EvidenceNode,
    MissingEvidence,
)
from ai_governance.decisions.evidence_builder import DecisionEvidenceBuilder
from ai_governance.decisions.explanation import DecisionExplanation
from ai_governance.decisions.models import (
    DecisionEvidenceReference,
    DecisionPolicyReference,
    DecisionProvenance,
    DecisionTarget,
    GovernanceDecision,
)
from ai_governance.decisions.outcome_mapping import (
    map_policy_outcomes_to_confidence,
    map_policy_outcomes_to_status,
)
from ai_governance.decisions.policies import (
    GovernancePolicy,
    GovernancePolicyEvaluator,
    PolicyEvaluationOutcome,
)
from ai_governance.decisions.reasoning_models import (
    GovernanceReasoningOutcome,
    GovernanceReasoningRequest,
    ReasoningEvidenceSummary,
)
from ai_governance.ontology import EntityType

REASONING_CREATED_AT = datetime(1970, 1, 1, tzinfo=UTC)


class GovernancePolicyProvider(Protocol):
    """
    Read-only policy lookup abstraction for governance reasoning.
    """

    def get_policies_for_target(
        self,
        target_type: DecisionTargetType,
        policy_ids: tuple[str, ...] = (),
    ) -> tuple[GovernancePolicy, ...]: ...


class InMemoryGovernancePolicyProvider:
    """
    Deterministic in-memory policy provider for tests and local reasoning.
    """

    def __init__(self, policies: Sequence[GovernancePolicy]) -> None:
        self._policies = tuple(
            sorted(
                policies,
                key=lambda policy: (policy.policy_id, policy.version),
            )
        )

    def get_policies_for_target(
        self,
        target_type: DecisionTargetType,
        policy_ids: tuple[str, ...] = (),
    ) -> tuple[GovernancePolicy, ...]:
        policy_id_filter = set(policy_ids)
        return tuple(
            policy
            for policy in self._policies
            if target_type in policy.target_types
            and (not policy_id_filter or policy.policy_id in policy_id_filter)
        )


class ReasoningEvidenceSummarizer:
    """
    Deterministic summarizer over an already-built evidence graph.
    """

    def summarize(
        self,
        evidence_graph: DecisionEvidenceGraph,
    ) -> ReasoningEvidenceSummary:
        metric_scores: dict[str, float] = {}
        metric_failures: list[str] = []
        drift_severity: str | None = None
        latest_job_status: str | None = None
        latest_audit_status: str | None = None
        ids_by_type = _ids_by_type(evidence_graph.nodes)

        for node in evidence_graph.nodes:
            if node.entity_type == EntityType.METRIC.value:
                metric_name = _node_name(node)
                score = _first_present(
                    node.attributes,
                    node.metadata,
                    ("score", "value", "metric_value"),
                )
                if isinstance(score, int | float):
                    metric_scores[_normalize_key(metric_name)] = float(score)
                if _node_status(node) in {"FAILED", "FAILURE", "ERROR"}:
                    metric_failures.append(_normalize_key(metric_name))
            elif node.entity_type == EntityType.DRIFT_ANALYSIS.value:
                drift_severity = _first_string(
                    node.attributes,
                    node.metadata,
                    ("severity", "drift_severity"),
                )
            elif node.entity_type == EntityType.JOB.value:
                latest_job_status = _node_status(node)
            elif node.entity_type == EntityType.MCP_AUDIT_RECORD.value:
                latest_audit_status = _node_status(node)

        return ReasoningEvidenceSummary(
            target_type=evidence_graph.target_type,
            target_id=evidence_graph.target_id,
            metric_scores=metric_scores,
            metric_failures=metric_failures,
            threshold_breaches=_threshold_breaches(evidence_graph.nodes),
            drift_severity=drift_severity,
            latest_job_status=latest_job_status,
            latest_audit_status=latest_audit_status,
            evaluation_result_ids=ids_by_type[EntityType.EVALUATION_RESULT.value],
            metric_ids=ids_by_type[EntityType.METRIC.value],
            drift_analysis_ids=ids_by_type[EntityType.DRIFT_ANALYSIS.value],
            leaderboard_ids=ids_by_type[EntityType.LEADERBOARD.value],
            job_ids=ids_by_type[EntityType.JOB.value],
            mcp_audit_ids=ids_by_type[EntityType.MCP_AUDIT_RECORD.value],
            policy_ids=ids_by_type[EntityType.POLICY.value],
            missing_evidence=evidence_graph.missing,
            metadata=dict(evidence_graph.metadata),
        )


class GovernanceReasoningEngine:
    """
    Deterministic orchestration service for governance reasoning.
    """

    def __init__(
        self,
        evidence_builder: DecisionEvidenceBuilder,
        evidence_summarizer: ReasoningEvidenceSummarizer,
        policy_evaluator: GovernancePolicyEvaluator,
        policy_provider: GovernancePolicyProvider,
    ) -> None:
        self._evidence_builder = evidence_builder
        self._evidence_summarizer = evidence_summarizer
        self._policy_evaluator = policy_evaluator
        self._policy_provider = policy_provider

    def reason(
        self,
        request: GovernanceReasoningRequest,
    ) -> GovernanceReasoningOutcome:
        evidence_graph = self._evidence_builder.build_for_target(
            request.target_type,
            request.target_id,
        )
        evidence_summary = self._evidence_summarizer.summarize(evidence_graph)
        policy_context = self._evidence_builder.build_policy_context(evidence_graph)
        request_resolver = getattr(
            self._policy_provider, "get_policies_for_request", None
        )
        policies = (
            request_resolver(request)
            if request_resolver is not None
            else self._policy_provider.get_policies_for_target(
                request.target_type,
                request.policy_ids,
            )
        )
        policy_outcomes = tuple(
            self._policy_evaluator.evaluate(policy, policy_context)
            for policy in policies
        )
        decision_status = map_policy_outcomes_to_status(policy_outcomes)
        confidence = map_policy_outcomes_to_confidence(
            policy_outcomes,
            evidence_summary.missing_evidence,
        )
        evidence_references = _evidence_references(evidence_summary)
        policy_references = _policy_references(policy_outcomes, policies)
        reason = _decision_reason(policy_outcomes)
        decision_id = _decision_id(
            request,
            evidence_summary,
            policy_outcomes,
        )
        decision = GovernanceDecision(
            decision_id=decision_id,
            decision_type=request.decision_type,
            status=decision_status,
            target=DecisionTarget(request.target_type, request.target_id),
            reason=reason,
            confidence=confidence,
            evidence=evidence_references,
            policies=policy_references,
            provenance=DecisionProvenance(
                producer_type=DecisionProducerType.POLICY_ENGINE,
                producer_id=request.producer_id,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                created_at=REASONING_CREATED_AT,
            ),
            metadata=dict(request.metadata),
        )
        explanation = _explanation(
            decision,
            evidence_summary,
            policy_outcomes,
            evidence_references,
            policy_references,
        )
        return GovernanceReasoningOutcome(
            decision=decision,
            evidence_graph=evidence_graph,
            evidence_summary=evidence_summary,
            policy_outcomes=policy_outcomes,
            explanation=explanation,
        )


def _decision_reason(
    policy_outcomes: Sequence[PolicyEvaluationOutcome],
) -> str:
    matched_reasons = sorted(
        outcome.reason for outcome in policy_outcomes if outcome.matched
    )
    if matched_reasons:
        return matched_reasons[0]
    return "No policy produced a final decision."


def _evidence_references(
    evidence_summary: ReasoningEvidenceSummary,
) -> tuple[DecisionEvidenceReference, ...]:
    references: list[DecisionEvidenceReference] = []
    for evidence_type, ids in (
        ("EvaluationResult", evidence_summary.evaluation_result_ids),
        ("Metric", evidence_summary.metric_ids),
        ("DriftAnalysis", evidence_summary.drift_analysis_ids),
        ("Leaderboard", evidence_summary.leaderboard_ids),
        ("Job", evidence_summary.job_ids),
        ("MCPAuditRecord", evidence_summary.mcp_audit_ids),
        ("Policy", evidence_summary.policy_ids),
    ):
        references.extend(
            DecisionEvidenceReference(
                evidence_type=evidence_type,
                evidence_id=evidence_id,
                source="governance-reasoning-engine",
            )
            for evidence_id in ids
        )
    for missing in evidence_summary.missing_evidence:
        references.append(
            DecisionEvidenceReference(
                evidence_type="MissingEvidence",
                evidence_id=_missing_evidence_id(missing),
                source="governance-reasoning-engine",
                metadata={
                    "missing_evidence_type": missing.evidence_type,
                    "severity": missing.severity,
                },
            )
        )
    if not references:
        references.append(
            DecisionEvidenceReference(
                evidence_type="ReasoningEvidenceSummary",
                evidence_id=(
                    f"{evidence_summary.target_type.value}:{evidence_summary.target_id}"
                ),
                source="governance-reasoning-engine",
            )
        )
    return tuple(
        sorted(
            references,
            key=lambda reference: (
                reference.evidence_type,
                reference.evidence_id,
            ),
        )
    )


def _policy_references(
    policy_outcomes: Sequence[PolicyEvaluationOutcome],
    policies: Sequence[GovernancePolicy],
) -> tuple[DecisionPolicyReference, ...]:
    policy_map = {(policy.policy_id, policy.version): policy for policy in policies}
    references = []
    for outcome in policy_outcomes:
        if not outcome.matched:
            continue
        policy = policy_map.get((outcome.policy_id, outcome.policy_version))
        references.append(
            DecisionPolicyReference(
                policy_id=outcome.policy_id,
                policy_version=outcome.policy_version,
                policy_name=policy.name if policy is not None else None,
            )
        )
    return tuple(
        sorted(
            references,
            key=lambda reference: (
                reference.policy_id,
                reference.policy_version,
            ),
        )
    )


def _explanation(
    decision: GovernanceDecision,
    evidence_summary: ReasoningEvidenceSummary,
    policy_outcomes: Sequence[PolicyEvaluationOutcome],
    evidence_references: tuple[DecisionEvidenceReference, ...],
    policy_references: tuple[DecisionPolicyReference, ...],
) -> DecisionExplanation:
    reasons = _explanation_reasons(policy_outcomes, evidence_summary)
    return DecisionExplanation(
        decision_id=decision.decision_id,
        summary=_explanation_summary(decision),
        reasons=reasons,
        evidence_references=evidence_references,
        policy_references=policy_references,
        missing_evidence=evidence_summary.missing_evidence,
        metadata={"target_id": evidence_summary.target_id},
    )


def _explanation_summary(decision: GovernanceDecision) -> str:
    return (
        f"{decision.target.target_type.value} {decision.target.target_id} "
        f"was {decision.status.value.lower()} because {decision.reason}"
    )


def _explanation_reasons(
    policy_outcomes: Sequence[PolicyEvaluationOutcome],
    evidence_summary: ReasoningEvidenceSummary,
) -> tuple[str, ...]:
    reasons = sorted(outcome.reason for outcome in policy_outcomes if outcome.matched)
    reasons.extend(
        f"Critical missing evidence: {missing.evidence_type} - {missing.reason}"
        for missing in evidence_summary.missing_evidence
        if missing.severity == "CRITICAL"
    )
    if not reasons:
        reasons.append("No policy produced a final decision.")
    return tuple(reasons)


def _decision_id(
    request: GovernanceReasoningRequest,
    evidence_summary: ReasoningEvidenceSummary,
    policy_outcomes: Sequence[PolicyEvaluationOutcome],
) -> str:
    fingerprint = _stable_hash(
        {
            "target_type": request.target_type.value,
            "target_id": request.target_id,
            "decision_type": request.decision_type.value,
            "policy_ids": request.policy_ids,
            "evidence_summary": _summary_fingerprint(evidence_summary),
            "policy_outcomes": [
                {
                    "policy_id": outcome.policy_id,
                    "policy_version": outcome.policy_version,
                    "matched_rule_id": outcome.matched_rule_id,
                    "effect": outcome.effect.value,
                    "matched": outcome.matched,
                }
                for outcome in sorted(
                    policy_outcomes,
                    key=lambda item: (
                        item.policy_id,
                        item.policy_version,
                        item.matched_rule_id or "",
                    ),
                )
            ],
        }
    )
    return (
        f"decision:{request.target_type.value}:{request.target_id}:"
        f"{request.decision_type.value}:{fingerprint}"
    )


def _summary_fingerprint(
    evidence_summary: ReasoningEvidenceSummary,
) -> dict[str, Any]:
    return {
        "metric_scores": evidence_summary.metric_scores,
        "metric_failures": evidence_summary.metric_failures,
        "threshold_breaches": evidence_summary.threshold_breaches,
        "drift_severity": evidence_summary.drift_severity,
        "latest_job_status": evidence_summary.latest_job_status,
        "latest_audit_status": evidence_summary.latest_audit_status,
        "evaluation_result_ids": evidence_summary.evaluation_result_ids,
        "metric_ids": evidence_summary.metric_ids,
        "drift_analysis_ids": evidence_summary.drift_analysis_ids,
        "leaderboard_ids": evidence_summary.leaderboard_ids,
        "job_ids": evidence_summary.job_ids,
        "mcp_audit_ids": evidence_summary.mcp_audit_ids,
        "policy_ids": evidence_summary.policy_ids,
        "missing_evidence": [
            {
                "evidence_type": item.evidence_type,
                "reason": item.reason,
                "severity": item.severity,
            }
            for item in evidence_summary.missing_evidence
        ],
    }


def _stable_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _ids_by_type(
    nodes: Sequence[EvidenceNode],
) -> dict[str, tuple[str, ...]]:
    entity_types = (
        EntityType.EVALUATION_RESULT.value,
        EntityType.METRIC.value,
        EntityType.DRIFT_ANALYSIS.value,
        EntityType.LEADERBOARD.value,
        EntityType.JOB.value,
        EntityType.MCP_AUDIT_RECORD.value,
        EntityType.POLICY.value,
    )
    result: dict[str, list[str]] = {entity_type: [] for entity_type in entity_types}
    for node in nodes:
        if node.entity_type in result:
            result[node.entity_type].append(node.entity_id)
    return {
        entity_type: tuple(sorted(entity_ids))
        for entity_type, entity_ids in result.items()
    }


def _threshold_breaches(nodes: Sequence[EvidenceNode]) -> tuple[str, ...]:
    breaches = []
    for node in nodes:
        if node.entity_type != EntityType.METRIC.value:
            continue
        breach = _first_present(
            node.attributes,
            node.metadata,
            ("threshold_breach", "breached_threshold"),
        )
        if breach is True:
            breaches.append(_normalize_key(_node_name(node)))
        elif isinstance(breach, str) and breach.strip():
            breaches.append(breach)
    return tuple(sorted(breaches))


def _node_name(node: EvidenceNode) -> str:
    return (
        _first_string(
            node.attributes,
            node.metadata,
            ("metric_name", "name", "label"),
        )
        or node.label
        or node.entity_id
    )


def _node_status(node: EvidenceNode) -> str | None:
    status = _first_string(
        node.attributes,
        node.metadata,
        ("status", "lifecycle"),
    )
    if status is None:
        status = node.lifecycle
    return status.upper() if isinstance(status, str) else None


def _first_string(
    attributes: Mapping[str, Any],
    metadata: Mapping[str, Any],
    names: tuple[str, ...],
) -> str | None:
    value = _first_present(attributes, metadata, names)
    return value if isinstance(value, str) and value.strip() else None


def _first_present(
    attributes: Mapping[str, Any],
    metadata: Mapping[str, Any],
    names: tuple[str, ...],
) -> Any | None:
    for mapping in (attributes, metadata):
        for name in names:
            if name in mapping and mapping[name] is not None:
                return mapping[name]
    return None


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _missing_evidence_id(missing: MissingEvidence) -> str:
    return _stable_hash(
        {
            "evidence_type": missing.evidence_type,
            "severity": missing.severity,
            "reason": missing.reason,
        }
    )
