from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from kavach.decisions import (
    DecisionAuditAction,
    DecisionAuditRecord,
    DecisionConfidenceLevel,
    DecisionEvidenceReference,
    DecisionExplanation,
    DecisionPolicyReference,
    DecisionProducerType,
    DecisionProvenance,
    DecisionStatus,
    DecisionSupersession,
    DecisionTarget,
    DecisionType,
    GovernanceDecision,
    MissingEvidence,
)


class GovernanceDecisionPersistenceMapper:
    """
    Maps governance decisions, explanations, and audit records to persistence.
    """

    @staticmethod
    def canonical_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @classmethod
    def to_persistence_record(
        cls,
        decision: GovernanceDecision,
        explanation: DecisionExplanation | None = None,
    ) -> dict[str, Any]:
        return {
            "decision_id": decision.decision_id,
            "decision_type": decision.decision_type.value,
            "status": decision.status.value,
            "target_type": decision.target.target_type.value,
            "target_id": decision.target.target_id,
            "reason": decision.reason,
            "confidence": decision.confidence.value,
            "evidence_json": cls.canonical_json(
                [_evidence_reference_to_dict(item) for item in decision.evidence]
            ),
            "policies_json": cls.canonical_json(
                [_policy_reference_to_dict(item) for item in decision.policies]
            ),
            "provenance_json": cls.canonical_json(
                _provenance_to_dict(decision.provenance)
            ),
            "supersession_json": cls.canonical_json(
                _supersession_to_dict(decision.supersession)
            ),
            "explanation_json": (
                cls.canonical_json(_explanation_to_dict(explanation))
                if explanation is not None
                else None
            ),
            "metadata_json": cls.canonical_json(decision.metadata),
            "created_at": decision.provenance.created_at.isoformat(),
            "finalized_at": _datetime_to_text(decision.finalized_at),
            "archived_at": _datetime_to_text(decision.archived_at),
        }

    @staticmethod
    def from_persistence_record(record: Mapping[str, Any]) -> GovernanceDecision:
        provenance = json.loads(record["provenance_json"])
        supersession = json.loads(record["supersession_json"])
        return GovernanceDecision(
            decision_id=record["decision_id"],
            decision_type=DecisionType(record["decision_type"]),
            status=DecisionStatus(record["status"]),
            target=DecisionTarget(record["target_type"], record["target_id"]),
            reason=record["reason"],
            confidence=DecisionConfidenceLevel(record["confidence"]),
            evidence=tuple(
                _evidence_reference_from_dict(item)
                for item in json.loads(record["evidence_json"])
            ),
            policies=tuple(
                _policy_reference_from_dict(item)
                for item in json.loads(record["policies_json"])
            ),
            provenance=_provenance_from_dict(provenance),
            supersession=_supersession_from_dict(supersession),
            metadata=json.loads(record["metadata_json"]),
            finalized_at=_datetime_from_text(record["finalized_at"]),
            archived_at=_datetime_from_text(record["archived_at"]),
        )

    @classmethod
    def from_persistence_records(
        cls,
        records: Sequence[Mapping[str, Any]],
    ) -> tuple[GovernanceDecision, ...]:
        return tuple(cls.from_persistence_record(record) for record in records)

    @classmethod
    def explanation_from_persistence_record(
        cls,
        record: Mapping[str, Any],
    ) -> DecisionExplanation | None:
        if record["explanation_json"] is None:
            return None
        return _explanation_from_dict(json.loads(record["explanation_json"]))

    @classmethod
    def audit_to_persistence_record(
        cls,
        record: DecisionAuditRecord,
    ) -> dict[str, Any]:
        return {
            "audit_id": record.audit_id,
            "decision_id": record.decision_id,
            "action": record.action.value,
            "actor_id": record.actor_id,
            "producer_id": record.producer_id,
            "correlation_id": record.correlation_id,
            "request_id": record.request_id,
            "reason": record.reason,
            "created_at": record.created_at.isoformat(),
            "metadata_json": cls.canonical_json(record.metadata),
        }

    @staticmethod
    def audit_from_persistence_record(
        record: Mapping[str, Any],
    ) -> DecisionAuditRecord:
        return DecisionAuditRecord(
            audit_id=record["audit_id"],
            decision_id=record["decision_id"],
            action=DecisionAuditAction(record["action"]),
            actor_id=record["actor_id"],
            producer_id=record["producer_id"],
            correlation_id=record["correlation_id"],
            request_id=record["request_id"],
            reason=record["reason"],
            created_at=datetime.fromisoformat(record["created_at"]),
            metadata=json.loads(record["metadata_json"]),
        )

    @classmethod
    def audit_from_persistence_records(
        cls,
        records: Sequence[Mapping[str, Any]],
    ) -> tuple[DecisionAuditRecord, ...]:
        return tuple(cls.audit_from_persistence_record(record) for record in records)


def _evidence_reference_to_dict(
    reference: DecisionEvidenceReference,
) -> dict[str, Any]:
    return {
        "evidence_type": reference.evidence_type,
        "evidence_id": reference.evidence_id,
        "relationship_type": reference.relationship_type,
        "source": reference.source,
        "metadata": dict(reference.metadata),
    }


def _evidence_reference_from_dict(
    value: Mapping[str, Any],
) -> DecisionEvidenceReference:
    return DecisionEvidenceReference(
        evidence_type=value["evidence_type"],
        evidence_id=value["evidence_id"],
        relationship_type=value.get("relationship_type"),
        source=value.get("source"),
        metadata=value.get("metadata") or {},
    )


def _policy_reference_to_dict(
    reference: DecisionPolicyReference,
) -> dict[str, Any]:
    return {
        "policy_id": reference.policy_id,
        "policy_version": reference.policy_version,
        "policy_name": reference.policy_name,
        "metadata": dict(reference.metadata),
    }


def _policy_reference_from_dict(
    value: Mapping[str, Any],
) -> DecisionPolicyReference:
    return DecisionPolicyReference(
        policy_id=value["policy_id"],
        policy_version=value["policy_version"],
        policy_name=value.get("policy_name"),
        metadata=value.get("metadata") or {},
    )


def _provenance_to_dict(provenance: DecisionProvenance) -> dict[str, Any]:
    return {
        "producer_type": provenance.producer_type.value,
        "producer_id": provenance.producer_id,
        "actor_id": provenance.actor_id,
        "correlation_id": provenance.correlation_id,
        "request_id": provenance.request_id,
        "created_at": provenance.created_at.isoformat(),
    }


def _provenance_from_dict(value: Mapping[str, Any]) -> DecisionProvenance:
    return DecisionProvenance(
        producer_type=DecisionProducerType(value["producer_type"]),
        producer_id=value["producer_id"],
        actor_id=value.get("actor_id"),
        correlation_id=value.get("correlation_id"),
        request_id=value.get("request_id"),
        created_at=datetime.fromisoformat(value["created_at"]),
    )


def _supersession_to_dict(
    supersession: DecisionSupersession,
) -> dict[str, Any]:
    return {
        "supersedes_decision_id": supersession.supersedes_decision_id,
        "superseded_by_decision_id": supersession.superseded_by_decision_id,
        "supersession_reason": supersession.supersession_reason,
    }


def _supersession_from_dict(value: Mapping[str, Any]) -> DecisionSupersession:
    return DecisionSupersession(
        supersedes_decision_id=value.get("supersedes_decision_id"),
        superseded_by_decision_id=value.get("superseded_by_decision_id"),
        supersession_reason=value.get("supersession_reason"),
    )


def _explanation_to_dict(
    explanation: DecisionExplanation,
) -> dict[str, Any]:
    return {
        "decision_id": explanation.decision_id,
        "summary": explanation.summary,
        "reasons": list(explanation.reasons),
        "evidence_references": [
            _evidence_reference_to_dict(item)
            for item in explanation.evidence_references
        ],
        "policy_references": [
            _policy_reference_to_dict(item)
            for item in explanation.policy_references
        ],
        "missing_evidence": [
            _missing_evidence_to_dict(item)
            for item in explanation.missing_evidence
        ],
        "metadata": dict(explanation.metadata),
    }


def _explanation_from_dict(value: Mapping[str, Any]) -> DecisionExplanation:
    return DecisionExplanation(
        decision_id=value["decision_id"],
        summary=value["summary"],
        reasons=tuple(value["reasons"]),
        evidence_references=tuple(
            _evidence_reference_from_dict(item)
            for item in value["evidence_references"]
        ),
        policy_references=tuple(
            _policy_reference_from_dict(item)
            for item in value["policy_references"]
        ),
        missing_evidence=tuple(
            _missing_evidence_from_dict(item)
            for item in value["missing_evidence"]
        ),
        metadata=value.get("metadata") or {},
    )


def _missing_evidence_to_dict(missing: MissingEvidence) -> dict[str, Any]:
    return {
        "evidence_type": missing.evidence_type,
        "reason": missing.reason,
        "severity": missing.severity,
        "metadata": dict(missing.metadata),
    }


def _missing_evidence_from_dict(value: Mapping[str, Any]) -> MissingEvidence:
    return MissingEvidence(
        evidence_type=value["evidence_type"],
        reason=value["reason"],
        severity=value["severity"],
        metadata=value.get("metadata") or {},
    )


def _datetime_to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime_from_text(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None
