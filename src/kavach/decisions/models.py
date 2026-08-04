from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kavach.decisions.enums import (
    DecisionConfidenceLevel,
    DecisionProducerType,
    DecisionStatus,
    DecisionTargetType,
    DecisionType,
)
from kavach.decisions.exceptions import DecisionValidationError
from kavach.decisions.validation import (
    coerce_enum,
    copy_mapping,
    require_non_empty,
    require_optional_non_empty,
    require_timezone_aware,
)
from kavach.ontology.enums import EntityType


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class DecisionTarget:
    """
    Ontology entity that a governance decision applies to.
    """

    target_type: DecisionTargetType | str
    target_id: str

    def __post_init__(self) -> None:
        require_non_empty("target_id", self.target_id)

        target_type = coerce_enum(
            "target_type",
            DecisionTargetType,
            self.target_type,
        )
        try:
            EntityType(target_type.value)
        except ValueError as exc:
            raise DecisionValidationError(
                f"Decision target_type is not ontology-aligned: "
                f"{target_type.value!r}."
            ) from exc

        object.__setattr__(self, "target_type", target_type)


@dataclass(frozen=True)
class DecisionEvidenceReference:
    """
    Reference to evidence used by a governance decision.
    """

    evidence_type: str
    evidence_id: str
    relationship_type: str | None = None
    source: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("evidence_type", self.evidence_type)
        require_non_empty("evidence_id", self.evidence_id)
        require_optional_non_empty("relationship_type", self.relationship_type)
        require_optional_non_empty("source", self.source)
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class DecisionPolicyReference:
    """
    Reference to a policy considered by a governance decision.
    """

    policy_id: str
    policy_version: str
    policy_name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("policy_id", self.policy_id)
        require_non_empty("policy_version", self.policy_version)
        require_optional_non_empty("policy_name", self.policy_name)
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class DecisionProvenance:
    """
    Where, when, and by whom a governance decision was produced.
    """

    producer_type: DecisionProducerType | str
    producer_id: str
    actor_id: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        require_non_empty("producer_id", self.producer_id)
        require_optional_non_empty("actor_id", self.actor_id)
        require_optional_non_empty("correlation_id", self.correlation_id)
        require_optional_non_empty("request_id", self.request_id)
        require_timezone_aware("created_at", self.created_at)
        object.__setattr__(
            self,
            "producer_type",
            coerce_enum(
                "producer_type",
                DecisionProducerType,
                self.producer_type,
            ),
        )


@dataclass(frozen=True)
class DecisionSupersession:
    """
    Links a governance decision to decisions that replace or are replaced by it.
    """

    supersedes_decision_id: str | None = None
    superseded_by_decision_id: str | None = None
    supersession_reason: str | None = None

    def __post_init__(self) -> None:
        require_optional_non_empty(
            "supersedes_decision_id",
            self.supersedes_decision_id,
        )
        require_optional_non_empty(
            "superseded_by_decision_id",
            self.superseded_by_decision_id,
        )
        require_optional_non_empty(
            "supersession_reason",
            self.supersession_reason,
        )

        if (
            self.supersedes_decision_id is not None
            and self.superseded_by_decision_id is not None
            and self.supersedes_decision_id == self.superseded_by_decision_id
        ):
            raise DecisionValidationError(
                "Decision cannot supersede and be superseded by the same "
                "decision."
            )


@dataclass(frozen=True)
class GovernanceDecision:
    """
    Evidence-backed governed outcome produced by Kavach.
    """

    decision_id: str
    decision_type: DecisionType | str
    status: DecisionStatus | str
    target: DecisionTarget
    reason: str
    confidence: DecisionConfidenceLevel | str
    evidence: Sequence[DecisionEvidenceReference]
    policies: Sequence[DecisionPolicyReference]
    provenance: DecisionProvenance
    supersession: DecisionSupersession = field(
        default_factory=DecisionSupersession
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)
    finalized_at: datetime | None = None
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        require_non_empty("decision_id", self.decision_id)
        require_non_empty("reason", self.reason)

        decision_type = coerce_enum(
            "decision_type",
            DecisionType,
            self.decision_type,
        )
        status = coerce_enum("status", DecisionStatus, self.status)
        confidence = coerce_enum(
            "confidence",
            DecisionConfidenceLevel,
            self.confidence,
        )
        evidence = tuple(self.evidence)
        policies = tuple(self.policies)

        if not evidence:
            raise DecisionValidationError(
                "Decision evidence must contain at least one reference."
            )

        if not isinstance(self.target, DecisionTarget):
            raise DecisionValidationError(
                "Decision target must be a DecisionTarget."
            )

        if not isinstance(self.provenance, DecisionProvenance):
            raise DecisionValidationError(
                "Decision provenance must be a DecisionProvenance."
            )

        if not isinstance(self.supersession, DecisionSupersession):
            raise DecisionValidationError(
                "Decision supersession must be a DecisionSupersession."
            )

        for reference in evidence:
            if not isinstance(reference, DecisionEvidenceReference):
                raise DecisionValidationError(
                    "Decision evidence entries must be "
                    "DecisionEvidenceReference instances."
                )

        for reference in policies:
            if not isinstance(reference, DecisionPolicyReference):
                raise DecisionValidationError(
                    "Decision policy entries must be "
                    "DecisionPolicyReference instances."
                )

        if self.finalized_at is not None:
            require_timezone_aware("finalized_at", self.finalized_at)

        if self.archived_at is not None:
            require_timezone_aware("archived_at", self.archived_at)

        self._validate_supersession_references()

        object.__setattr__(self, "decision_type", decision_type)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "policies", policies)
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))

    @classmethod
    def proposed(
        cls,
        *,
        decision_id: str,
        target: DecisionTarget,
        reason: str,
        evidence: Sequence[DecisionEvidenceReference],
        provenance: DecisionProvenance,
        decision_type: DecisionType | str = DecisionType.RECOMMEND,
        confidence: DecisionConfidenceLevel | str = (
            DecisionConfidenceLevel.MEDIUM
        ),
        policies: Sequence[DecisionPolicyReference] = (),
        supersession: DecisionSupersession | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> GovernanceDecision:
        return cls(
            decision_id=decision_id,
            decision_type=decision_type,
            status=DecisionStatus.PROPOSED,
            target=target,
            reason=reason,
            confidence=confidence,
            evidence=evidence,
            policies=policies,
            provenance=provenance,
            supersession=supersession or DecisionSupersession(),
            metadata=metadata or {},
        )

    @classmethod
    def approved(
        cls,
        *,
        decision_id: str,
        target: DecisionTarget,
        reason: str,
        evidence: Sequence[DecisionEvidenceReference],
        provenance: DecisionProvenance,
        confidence: DecisionConfidenceLevel | str = DecisionConfidenceLevel.HIGH,
        policies: Sequence[DecisionPolicyReference] = (),
        supersession: DecisionSupersession | None = None,
        metadata: Mapping[str, Any] | None = None,
        finalized_at: datetime | None = None,
    ) -> GovernanceDecision:
        return cls(
            decision_id=decision_id,
            decision_type=DecisionType.APPROVE,
            status=DecisionStatus.APPROVED,
            target=target,
            reason=reason,
            confidence=confidence,
            evidence=evidence,
            policies=policies,
            provenance=provenance,
            supersession=supersession or DecisionSupersession(),
            metadata=metadata or {},
            finalized_at=finalized_at,
        )

    @classmethod
    def rejected(
        cls,
        *,
        decision_id: str,
        target: DecisionTarget,
        reason: str,
        evidence: Sequence[DecisionEvidenceReference],
        provenance: DecisionProvenance,
        confidence: DecisionConfidenceLevel | str = DecisionConfidenceLevel.HIGH,
        policies: Sequence[DecisionPolicyReference] = (),
        supersession: DecisionSupersession | None = None,
        metadata: Mapping[str, Any] | None = None,
        finalized_at: datetime | None = None,
    ) -> GovernanceDecision:
        return cls(
            decision_id=decision_id,
            decision_type=DecisionType.REJECT,
            status=DecisionStatus.REJECTED,
            target=target,
            reason=reason,
            confidence=confidence,
            evidence=evidence,
            policies=policies,
            provenance=provenance,
            supersession=supersession or DecisionSupersession(),
            metadata=metadata or {},
            finalized_at=finalized_at,
        )

    @classmethod
    def blocked(
        cls,
        *,
        decision_id: str,
        target: DecisionTarget,
        reason: str,
        evidence: Sequence[DecisionEvidenceReference],
        provenance: DecisionProvenance,
        confidence: DecisionConfidenceLevel | str = DecisionConfidenceLevel.HIGH,
        policies: Sequence[DecisionPolicyReference] = (),
        supersession: DecisionSupersession | None = None,
        metadata: Mapping[str, Any] | None = None,
        finalized_at: datetime | None = None,
    ) -> GovernanceDecision:
        return cls(
            decision_id=decision_id,
            decision_type=DecisionType.BLOCK,
            status=DecisionStatus.BLOCKED,
            target=target,
            reason=reason,
            confidence=confidence,
            evidence=evidence,
            policies=policies,
            provenance=provenance,
            supersession=supersession or DecisionSupersession(),
            metadata=metadata or {},
            finalized_at=finalized_at,
        )

    def is_finalized(self) -> bool:
        return self.status in {
            DecisionStatus.APPROVED,
            DecisionStatus.REJECTED,
            DecisionStatus.BLOCKED,
            DecisionStatus.SUPERSEDED,
            DecisionStatus.ARCHIVED,
        }

    def is_superseded(self) -> bool:
        return (
            self.status == DecisionStatus.SUPERSEDED
            or self.supersession.superseded_by_decision_id is not None
        )

    def requires_human_review(self) -> bool:
        return (
            self.status == DecisionStatus.PROPOSED
            and self.confidence == DecisionConfidenceLevel.LOW
        )

    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(reference.evidence_id for reference in self.evidence)

    def policy_ids(self) -> tuple[str, ...]:
        return tuple(reference.policy_id for reference in self.policies)

    def _validate_supersession_references(self) -> None:
        if self.supersession.supersedes_decision_id == self.decision_id:
            raise DecisionValidationError(
                "Decision cannot supersede itself."
            )

        if self.supersession.superseded_by_decision_id == self.decision_id:
            raise DecisionValidationError(
                "Decision cannot be superseded by itself."
            )
