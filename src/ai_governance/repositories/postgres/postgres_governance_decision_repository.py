from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.decisions import (
    DecisionAuditAction,
    DecisionAuditRecord,
    DecisionExplanation,
    DecisionStatus,
    DecisionSupersession,
    DecisionTargetType,
    GovernanceDecision,
)
from ai_governance.decisions.events import (
    GOVERNANCE_DECISION_ARCHIVED,
    GOVERNANCE_DECISION_CREATED,
    GOVERNANCE_DECISION_SUPERSEDED,
)
from ai_governance.decisions.exceptions import DecisionValidationError
from ai_governance.ontology.enums import EntityType
from ai_governance.ontology.synchronization.events import (
    OntologySyncEventPublisherProtocol,
)
from ai_governance.repositories.governance_decision_repository import (
    GovernanceDecisionRepository,
)
from ai_governance.repositories.mappers.governance_decision_persistence_mapper import (
    GovernanceDecisionPersistenceMapper,
)
from ai_governance.repositories.postgres._record_adapter import with_jsonb_fields


@final
class PostgresGovernanceDecisionRepository(GovernanceDecisionRepository):
    """
    PostgreSQL implementation of the GovernanceDecisionRepository contract.
    """

    _UPSERT_DECISION_SQL = """
    INSERT INTO governance_decision (
        decision_id,
        decision_type,
        status,
        target_type,
        target_id,
        reason,
        confidence,
        evidence_json,
        policies_json,
        provenance_json,
        supersession_json,
        explanation_json,
        metadata_json,
        created_at,
        finalized_at,
        archived_at
    )
    VALUES (
        %(decision_id)s,
        %(decision_type)s,
        %(status)s,
        %(target_type)s,
        %(target_id)s,
        %(reason)s,
        %(confidence)s,
        %(evidence_json)s,
        %(policies_json)s,
        %(provenance_json)s,
        %(supersession_json)s,
        %(explanation_json)s,
        %(metadata_json)s,
        %(created_at)s,
        %(finalized_at)s,
        %(archived_at)s
    )
    ON CONFLICT (decision_id)
    DO UPDATE SET
        decision_type = EXCLUDED.decision_type,
        status = EXCLUDED.status,
        target_type = EXCLUDED.target_type,
        target_id = EXCLUDED.target_id,
        reason = EXCLUDED.reason,
        confidence = EXCLUDED.confidence,
        evidence_json = EXCLUDED.evidence_json,
        policies_json = EXCLUDED.policies_json,
        provenance_json = EXCLUDED.provenance_json,
        supersession_json = EXCLUDED.supersession_json,
        explanation_json = EXCLUDED.explanation_json,
        metadata_json = EXCLUDED.metadata_json,
        created_at = EXCLUDED.created_at,
        finalized_at = EXCLUDED.finalized_at,
        archived_at = EXCLUDED.archived_at
    """

    _INSERT_AUDIT_SQL = """
    INSERT INTO governance_decision_audit (
        audit_id,
        decision_id,
        action,
        actor_id,
        producer_id,
        correlation_id,
        request_id,
        reason,
        created_at,
        metadata_json
    )
    VALUES (
        %(audit_id)s,
        %(decision_id)s,
        %(action)s,
        %(actor_id)s,
        %(producer_id)s,
        %(correlation_id)s,
        %(request_id)s,
        %(reason)s,
        %(created_at)s,
        %(metadata_json)s
    )
    ON CONFLICT (audit_id)
    DO UPDATE SET
        decision_id = EXCLUDED.decision_id,
        action = EXCLUDED.action,
        actor_id = EXCLUDED.actor_id,
        producer_id = EXCLUDED.producer_id,
        correlation_id = EXCLUDED.correlation_id,
        request_id = EXCLUDED.request_id,
        reason = EXCLUDED.reason,
        created_at = EXCLUDED.created_at,
        metadata_json = EXCLUDED.metadata_json
    """

    _SELECT_DECISION_COLUMNS = """
    SELECT
        decision_id,
        decision_type,
        status,
        target_type,
        target_id,
        reason,
        confidence,
        evidence_json::text AS evidence_json,
        policies_json::text AS policies_json,
        provenance_json::text AS provenance_json,
        supersession_json::text AS supersession_json,
        explanation_json::text AS explanation_json,
        metadata_json::text AS metadata_json,
        created_at::text AS created_at,
        finalized_at::text AS finalized_at,
        archived_at::text AS archived_at
    FROM governance_decision
    """

    _SELECT_AUDIT_COLUMNS = """
    SELECT
        audit_id,
        decision_id,
        action,
        actor_id,
        producer_id,
        correlation_id,
        request_id,
        reason,
        created_at::text AS created_at,
        metadata_json::text AS metadata_json
    FROM governance_decision_audit
    """

    def __init__(
        self,
        database: PostgresDatabase,
        *,
        ontology_event_publisher: OntologySyncEventPublisherProtocol | None = None,
    ) -> None:
        self._database = database
        self._ontology_event_publisher = ontology_event_publisher

    def save(self, decision: GovernanceDecision) -> GovernanceDecision:
        return self._save(decision)

    def save_with_explanation(
        self,
        decision: GovernanceDecision,
        explanation: DecisionExplanation,
    ) -> GovernanceDecision:
        return self._save(decision, explanation=explanation)

    def get(self, decision_id: str) -> GovernanceDecision | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_DECISION_COLUMNS} "
                "WHERE decision_id = %(decision_id)s",
                {"decision_id": decision_id},
            ).fetchone()

        if row is None:
            return None

        return GovernanceDecisionPersistenceMapper.from_persistence_record(row)

    def get_explanation(
        self,
        decision_id: str,
    ) -> DecisionExplanation | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT explanation_json::text AS explanation_json "
                "FROM governance_decision "
                "WHERE decision_id = %(decision_id)s",
                {"decision_id": decision_id},
            ).fetchone()

        if row is None:
            return None

        return GovernanceDecisionPersistenceMapper.explanation_from_persistence_record(
            row
        )

    def find_by_target(
        self,
        target_type: DecisionTargetType,
        target_id: str,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_DECISION_COLUMNS} "
                "WHERE target_type = %(target_type)s "
                "AND target_id = %(target_id)s "
                "ORDER BY created_at DESC, decision_id "
                "LIMIT %(limit)s",
                {
                    "target_type": target_type.value,
                    "target_id": target_id,
                    "limit": limit,
                },
            ).fetchall()

        return GovernanceDecisionPersistenceMapper.from_persistence_records(rows)

    def find_by_status(
        self,
        status: DecisionStatus,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_DECISION_COLUMNS} "
                "WHERE status = %(status)s "
                "ORDER BY created_at DESC, decision_id "
                "LIMIT %(limit)s",
                {"status": status.value, "limit": limit},
            ).fetchall()

        return GovernanceDecisionPersistenceMapper.from_persistence_records(rows)

    def find_by_correlation_id(
        self,
        correlation_id: str,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_DECISION_COLUMNS} "
                "WHERE provenance_json ->> 'correlation_id' = %(correlation_id)s "
                "ORDER BY created_at DESC, decision_id "
                "LIMIT %(limit)s",
                {"correlation_id": correlation_id, "limit": limit},
            ).fetchall()

        return GovernanceDecisionPersistenceMapper.from_persistence_records(rows)

    def find_by_request_id(
        self,
        request_id: str,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_DECISION_COLUMNS} "
                "WHERE provenance_json ->> 'request_id' = %(request_id)s "
                "ORDER BY created_at DESC, decision_id "
                "LIMIT %(limit)s",
                {"request_id": request_id, "limit": limit},
            ).fetchall()

        return GovernanceDecisionPersistenceMapper.from_persistence_records(rows)

    def list(
        self,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_DECISION_COLUMNS} "
                "ORDER BY created_at DESC, decision_id "
                "LIMIT %(limit)s",
                {"limit": limit},
            ).fetchall()

        return GovernanceDecisionPersistenceMapper.from_persistence_records(rows)

    def save_audit(
        self,
        record: DecisionAuditRecord,
    ) -> DecisionAuditRecord:
        persistence_record = with_jsonb_fields(
            GovernanceDecisionPersistenceMapper.audit_to_persistence_record(
                record
            ),
            "metadata_json",
        )
        with self._database.connect() as connection:
            try:
                connection.execute(self._INSERT_AUDIT_SQL, persistence_record)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return record

    def find_audit_by_decision(
        self,
        decision_id: str,
        *,
        limit: int = 100,
    ) -> tuple[DecisionAuditRecord, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_AUDIT_COLUMNS} "
                "WHERE decision_id = %(decision_id)s "
                "ORDER BY created_at, audit_id "
                "LIMIT %(limit)s",
                {"decision_id": decision_id, "limit": limit},
            ).fetchall()

        return GovernanceDecisionPersistenceMapper.audit_from_persistence_records(
            rows
        )

    def supersede(
        self,
        old_decision_id: str,
        new_decision: GovernanceDecision,
        *,
        reason: str,
    ) -> GovernanceDecision:
        old_decision = self.get(old_decision_id)
        if old_decision is None:
            raise DecisionValidationError(
                f"Governance decision {old_decision_id!r} does not exist."
            )
        if old_decision.supersession.superseded_by_decision_id is not None:
            raise DecisionValidationError(
                f"Governance decision {old_decision_id!r} is already superseded."
            )

        superseded_old = replace(
            old_decision,
            status=DecisionStatus.SUPERSEDED,
            supersession=DecisionSupersession(
                supersedes_decision_id=(
                    old_decision.supersession.supersedes_decision_id
                ),
                superseded_by_decision_id=new_decision.decision_id,
                supersession_reason=reason,
            ),
        )
        replacement = replace(
            new_decision,
            supersession=DecisionSupersession(
                supersedes_decision_id=old_decision_id,
                superseded_by_decision_id=(
                    new_decision.supersession.superseded_by_decision_id
                ),
                supersession_reason=reason,
            ),
        )

        self._save(superseded_old, publish_created=False, enforce_finalized=False)
        saved = self._save(replacement)
        self.save_audit(
            DecisionAuditRecord(
                decision_id=old_decision_id,
                action=DecisionAuditAction.SUPERSEDED,
                actor_id=replacement.provenance.actor_id,
                producer_id=replacement.provenance.producer_id,
                correlation_id=replacement.provenance.correlation_id,
                request_id=replacement.provenance.request_id,
                reason=reason,
                metadata={"superseded_by_decision_id": replacement.decision_id},
            )
        )
        self._publish(GOVERNANCE_DECISION_SUPERSEDED, superseded_old)
        return saved

    def archive(
        self,
        decision_id: str,
        *,
        reason: str,
    ) -> GovernanceDecision:
        decision = self.get(decision_id)
        if decision is None:
            raise DecisionValidationError(
                f"Governance decision {decision_id!r} does not exist."
            )
        if decision.status == DecisionStatus.ARCHIVED:
            return decision

        archived = replace(
            decision,
            status=DecisionStatus.ARCHIVED,
            archived_at=datetime.now(UTC),
        )
        saved = self._save(
            archived,
            publish_created=False,
            enforce_finalized=False,
        )
        self.save_audit(
            DecisionAuditRecord(
                decision_id=decision_id,
                action=DecisionAuditAction.ARCHIVED,
                actor_id=archived.provenance.actor_id,
                producer_id=archived.provenance.producer_id,
                correlation_id=archived.provenance.correlation_id,
                request_id=archived.provenance.request_id,
                reason=reason,
            )
        )
        self._publish(GOVERNANCE_DECISION_ARCHIVED, archived)
        return saved

    def _save(
        self,
        decision: GovernanceDecision,
        *,
        explanation: DecisionExplanation | None = None,
        publish_created: bool = True,
        enforce_finalized: bool = True,
    ) -> GovernanceDecision:
        existing = self.get(decision.decision_id)
        existing_explanation = (
            self.get_explanation(decision.decision_id)
            if existing is not None and explanation is not None
            else None
        )
        if (
            existing is not None
            and enforce_finalized
            and existing.is_finalized()
        ):
            if existing == decision and (
                explanation is None or existing_explanation == explanation
            ):
                return decision
            raise DecisionValidationError(
                "Finalized governance decision cannot be mutated."
            )

        record = with_jsonb_fields(
            GovernanceDecisionPersistenceMapper.to_persistence_record(
                decision,
                explanation,
            ),
            "evidence_json",
            "policies_json",
            "provenance_json",
            "supersession_json",
            "explanation_json",
            "metadata_json",
        )
        with self._database.connect() as connection:
            try:
                connection.execute(self._UPSERT_DECISION_SQL, record)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        if existing is None and publish_created:
            self._publish(GOVERNANCE_DECISION_CREATED, decision)
        return decision

    def _publish(
        self,
        event_type: str,
        decision: GovernanceDecision,
    ) -> None:
        if self._ontology_event_publisher is None:
            return

        self._ontology_event_publisher.publish_entity_event(
            event_type,
            entity_type=EntityType.GOVERNANCE_DECISION.value,
            entity_id=decision.decision_id,
            correlation_id=decision.provenance.correlation_id,
            payload={
                "decision_id": decision.decision_id,
                "status": decision.status.value,
                "target_type": decision.target.target_type.value,
                "target_id": decision.target.target_id,
            },
        )
