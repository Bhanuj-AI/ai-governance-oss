from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.decisions import (
    DecisionAuditAction,
    DecisionEvidenceReference,
    DecisionExplanation,
    DecisionPolicyReference,
    DecisionProducerType,
    DecisionProvenance,
    DecisionStatus,
    DecisionTarget,
    DecisionTargetType,
    GovernanceDecision,
)
from kavach.decisions.events import (
    GOVERNANCE_DECISION_ARCHIVED,
    GOVERNANCE_DECISION_CREATED,
    GOVERNANCE_DECISION_SUPERSEDED,
)
from kavach.decisions.exceptions import DecisionValidationError
from kavach.repositories.sqlite import SQLiteGovernanceDecisionRepository


class _RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str | None]] = []

    def publish_entity_event(
        self,
        event_type: str,
        *,
        entity_type: str,
        entity_id: str,
        correlation_id: str | None = None,
        scope_identifier: str | None = None,
        payload: object | None = None,
    ) -> object:
        self.events.append((event_type, entity_id, correlation_id))
        return object()


def test_save_get_query_and_explanation_round_trip(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    decision = _decision()
    explanation = _explanation()

    repository.save_with_explanation(decision, explanation)

    assert repository.get("decision-1") == decision
    assert repository.get_explanation("decision-1") == explanation
    assert repository.find_by_target(
        DecisionTargetType.CANDIDATE,
        "candidate-1",
    ) == (decision,)
    assert repository.find_by_status(DecisionStatus.APPROVED) == (decision,)
    assert repository.find_by_correlation_id("correlation-1") == (decision,)
    assert repository.find_by_request_id("request-1") == (decision,)
    assert repository.list() == (decision,)


def test_finalized_decision_save_is_idempotent_but_not_mutable(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    decision = _decision()
    repository.save(decision)

    assert repository.save(decision) == decision

    with pytest.raises(DecisionValidationError):
        repository.save(
            replace(
                decision,
                reason="Mutated finalized reason.",
            )
        )


def test_supersede_preserves_old_decision_and_audits_lifecycle(
    tmp_path: Path,
) -> None:
    publisher = _RecordingPublisher()
    repository = _repository(tmp_path, publisher=publisher)
    old_decision = _decision()
    new_decision = _decision(
        decision_id="decision-2",
        reason="Candidate passed governance with fresher evidence.",
    )
    repository.save(old_decision)

    saved = repository.supersede(
        "decision-1",
        new_decision,
        reason="Evidence was refreshed.",
    )

    assert saved.supersession.supersedes_decision_id == "decision-1"
    superseded = repository.get("decision-1")
    assert superseded is not None
    assert superseded.status == DecisionStatus.SUPERSEDED
    assert superseded.supersession.superseded_by_decision_id == "decision-2"
    audit_records = repository.find_audit_by_decision("decision-1")
    assert audit_records[0].action == DecisionAuditAction.SUPERSEDED
    assert audit_records[0].metadata == {
        "superseded_by_decision_id": "decision-2"
    }
    assert [event[0] for event in publisher.events] == [
        GOVERNANCE_DECISION_CREATED,
        GOVERNANCE_DECISION_CREATED,
        GOVERNANCE_DECISION_SUPERSEDED,
    ]


def test_archive_marks_decision_and_publishes_event(tmp_path: Path) -> None:
    publisher = _RecordingPublisher()
    repository = _repository(tmp_path, publisher=publisher)
    repository.save(_decision())

    archived = repository.archive(
        "decision-1",
        reason="Decision is no longer current.",
    )

    assert archived.status == DecisionStatus.ARCHIVED
    assert archived.archived_at is not None
    assert repository.find_audit_by_decision(
        "decision-1"
    )[0].action == DecisionAuditAction.ARCHIVED
    assert publisher.events[-1][0] == GOVERNANCE_DECISION_ARCHIVED


def _repository(
    tmp_path: Path,
    *,
    publisher: _RecordingPublisher | None = None,
) -> SQLiteGovernanceDecisionRepository:
    database = SQLiteDatabase(tmp_path / "kavach.db")
    database.initialize()
    return SQLiteGovernanceDecisionRepository(
        database,
        ontology_event_publisher=publisher,
    )


def _decision(
    *,
    decision_id: str = "decision-1",
    reason: str = "Candidate passed governance.",
) -> GovernanceDecision:
    return GovernanceDecision.approved(
        decision_id=decision_id,
        target=DecisionTarget(
            target_type=DecisionTargetType.CANDIDATE,
            target_id="candidate-1",
        ),
        reason=reason,
        evidence=(
            DecisionEvidenceReference(
                evidence_type="EvaluationResult",
                evidence_id="evaluation-result-1",
            ),
        ),
        policies=(
            DecisionPolicyReference(
                policy_id="policy-1",
                policy_version="2026-07-02",
                policy_name="minimum-quality-gate",
            ),
        ),
        provenance=DecisionProvenance(
            producer_type=DecisionProducerType.POLICY_ENGINE,
            producer_id="policy-engine-1",
            actor_id="governance-admin",
            correlation_id="correlation-1",
            request_id="request-1",
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        ),
        finalized_at=datetime(2026, 7, 2, 1, tzinfo=UTC),
    )


def _explanation() -> DecisionExplanation:
    return DecisionExplanation(
        decision_id="decision-1",
        summary="Candidate passed governance.",
        reasons=("quality policy passed",),
        evidence_references=(
            DecisionEvidenceReference(
                evidence_type="EvaluationResult",
                evidence_id="evaluation-result-1",
            ),
        ),
        policy_references=(
            DecisionPolicyReference(
                policy_id="policy-1",
                policy_version="2026-07-02",
                policy_name="minimum-quality-gate",
            ),
        ),
        missing_evidence=(),
    )
