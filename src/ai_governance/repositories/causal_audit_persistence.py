from __future__ import annotations

from datetime import datetime
from typing import Any

from ai_governance.domain.causal_audit import (
    CausalAudit,
    CausalAuditClassification,
    CausalAuditStatus,
    CounterfactualReplayLineage,
    EvidenceInterventionStrategy,
    InterventionConfiguration,
    OutcomeScore,
    ToolEvidenceInfluence,
)


def audit_to_payload(audit: CausalAudit) -> dict[str, Any]:
    return {
        "audit_id": audit.audit_id,
        "organization_id": audit.organization_id,
        "project_id": audit.project_id,
        "execution_id": audit.execution_id,
        "agent_id": audit.agent_id,
        "status": audit.status.value,
        "methodology_version": audit.methodology_version,
        "evaluator_ref": audit.evaluator_ref,
        "intervention": {
            "strategy": audit.intervention.strategy.value,
            "counterfactual_samples": audit.intervention.counterfactual_samples,
            "strategy_version": audit.intervention.strategy_version,
            "seed": audit.intervention.seed,
            "configuration": dict(audit.intervention.configuration),
            "intervention_policy_id": audit.intervention.intervention_policy_id,
            "intervention_policy_version": audit.intervention.intervention_policy_version,
        },
        "request_fingerprint": audit.request_fingerprint,
        "created_by": audit.created_by,
        "created_at": audit.created_at.isoformat(),
        "updated_at": audit.updated_at.isoformat(),
        "started_at": audit.started_at.isoformat() if audit.started_at else None,
        "completed_at": audit.completed_at.isoformat() if audit.completed_at else None,
        "failure_code": audit.failure_code,
        "failure_reason": audit.failure_reason,
        "classification": audit.classification.value if audit.classification else None,
        "tool_call_results": [
            _result_to_payload(result) for result in audit.tool_call_results
        ],
        "diagnostics": dict(audit.diagnostics),
        "version": audit.version,
    }


def audit_from_payload(payload: dict[str, Any]) -> CausalAudit:
    intervention = payload["intervention"]
    return CausalAudit(
        audit_id=payload["audit_id"],
        organization_id=payload["organization_id"],
        project_id=payload.get("project_id"),
        execution_id=payload["execution_id"],
        agent_id=payload["agent_id"],
        status=CausalAuditStatus(payload["status"]),
        methodology_version=payload["methodology_version"],
        evaluator_ref=payload["evaluator_ref"],
        intervention=InterventionConfiguration(
            EvidenceInterventionStrategy(intervention["strategy"]),
            int(intervention["counterfactual_samples"]),
            intervention.get("strategy_version", "v1"),
            intervention.get("seed"),
            intervention.get("configuration", {}),
            intervention.get("intervention_policy_id"),
            intervention.get("intervention_policy_version"),
        ),
        request_fingerprint=payload["request_fingerprint"],
        created_by=payload["created_by"],
        created_at=datetime.fromisoformat(payload["created_at"]),
        updated_at=datetime.fromisoformat(payload["updated_at"]),
        started_at=datetime.fromisoformat(payload["started_at"])
        if payload.get("started_at")
        else None,
        completed_at=datetime.fromisoformat(payload["completed_at"])
        if payload.get("completed_at")
        else None,
        failure_code=payload.get("failure_code"),
        failure_reason=payload.get("failure_reason"),
        classification=CausalAuditClassification(payload["classification"])
        if payload.get("classification")
        else None,
        tool_call_results=tuple(
            _result_from_payload(item) for item in payload.get("tool_call_results", [])
        ),
        diagnostics=payload.get("diagnostics", {}),
        version=int(payload.get("version", 0)),
    )


def _score_to_payload(score: OutcomeScore) -> dict[str, Any]:
    return {
        "value": score.value,
        "method": score.method,
        "provider": score.provider,
        "evaluator_version": score.evaluator_version,
        "metadata": dict(score.metadata),
    }


def _score_from_payload(payload: dict[str, Any]) -> OutcomeScore:
    return OutcomeScore(
        float(payload["value"]),
        payload["method"],
        payload["provider"],
        payload["evaluator_version"],
        payload.get("metadata", {}),
    )


def _result_to_payload(result: ToolEvidenceInfluence) -> dict[str, Any]:
    return {
        "tool_call_id": result.tool_call_id,
        "tool_name": result.tool_name,
        "position": result.position,
        "intervention": {
            "strategy": result.intervention.strategy.value,
            "counterfactual_samples": result.intervention.counterfactual_samples,
            "strategy_version": result.intervention.strategy_version,
            "seed": result.intervention.seed,
            "configuration": dict(result.intervention.configuration),
            "intervention_policy_id": result.intervention.intervention_policy_id,
            "intervention_policy_version": result.intervention.intervention_policy_version,
        },
        "counterfactual_count": result.counterfactual_count,
        "baseline_score": _score_to_payload(result.baseline_score),
        "counterfactual_score": _score_to_payload(result.counterfactual_score),
        "influence_score": result.influence_score,
        "useful": result.useful,
        "harmful": result.harmful,
        "post_saturation": result.post_saturation,
        "counterfactual_replay_ids": list(result.counterfactual_replay_ids),
        "counterfactual_execution_ids": list(result.counterfactual_execution_ids),
        "evidence_references": list(result.evidence_references),
        "diagnostics": dict(result.diagnostics),
        "counterfactual_lineage": [
            {
                "replay_id": item.replay_id,
                "replay_execution_id": item.replay_execution_id,
                "replay_status": item.replay_status,
                "policy_id": item.policy_id,
                "policy_version": item.policy_version,
                "provider_id": item.provider_id,
                "provider_version": item.provider_version,
                "original_evidence_digest": item.original_evidence_digest,
                "counterfactual_evidence_reference": item.counterfactual_evidence_reference,
                "counterfactual_evidence_digest": item.counterfactual_evidence_digest,
                "intervention_digest": item.intervention_digest,
                "evaluator_score": _score_to_payload(item.evaluator_score),
            }
            for item in result.counterfactual_lineage
        ],
    }


def _result_from_payload(payload: dict[str, Any]) -> ToolEvidenceInfluence:
    intervention = payload["intervention"]
    return ToolEvidenceInfluence(
        tool_call_id=payload["tool_call_id"],
        tool_name=payload["tool_name"],
        position=int(payload["position"]),
        intervention=InterventionConfiguration(
            EvidenceInterventionStrategy(intervention["strategy"]),
            int(intervention["counterfactual_samples"]),
            intervention.get("strategy_version", "v1"),
            intervention.get("seed"),
            intervention.get("configuration", {}),
            intervention.get("intervention_policy_id"),
            intervention.get("intervention_policy_version"),
        ),
        counterfactual_count=int(payload["counterfactual_count"]),
        baseline_score=_score_from_payload(payload["baseline_score"]),
        counterfactual_score=_score_from_payload(payload["counterfactual_score"]),
        influence_score=float(payload["influence_score"]),
        useful=bool(payload["useful"]),
        harmful=bool(payload["harmful"]),
        post_saturation=bool(payload["post_saturation"]),
        counterfactual_replay_ids=tuple(payload.get("counterfactual_replay_ids", [])),
        counterfactual_execution_ids=tuple(
            payload.get("counterfactual_execution_ids", [])
        ),
        evidence_references=tuple(payload.get("evidence_references", [])),
        diagnostics=payload.get("diagnostics", {}),
        counterfactual_lineage=tuple(
            CounterfactualReplayLineage(
                replay_id=item["replay_id"],
                replay_execution_id=item["replay_execution_id"],
                replay_status=item["replay_status"],
                policy_id=item["policy_id"],
                policy_version=int(item["policy_version"]),
                provider_id=item["provider_id"],
                provider_version=item["provider_version"],
                original_evidence_digest=item["original_evidence_digest"],
                counterfactual_evidence_reference=item[
                    "counterfactual_evidence_reference"
                ],
                counterfactual_evidence_digest=item[
                    "counterfactual_evidence_digest"
                ],
                intervention_digest=item["intervention_digest"],
                evaluator_score=_score_from_payload(item["evaluator_score"]),
            )
            for item in payload.get("counterfactual_lineage", [])
        ),
    )
