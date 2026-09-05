from __future__ import annotations

import json

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.causal_audit import CausalAudit
from ai_governance.repositories.causal_audit_persistence import (
    audit_from_payload,
    audit_to_payload,
)
from ai_governance.repositories.causal_audit_repository import (
    CausalAuditListFilters,
    CausalAuditRepository,
)


class SQLiteCausalAuditRepository(CausalAuditRepository):
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(
        self, audit: CausalAudit, expected_version: int | None = None
    ) -> CausalAudit:
        payload = json.dumps(
            audit_to_payload(audit), sort_keys=True, separators=(",", ":")
        )
        with self._database.connect() as connection:
            existing = connection.execute(
                "SELECT version, status FROM causal_audit WHERE organization_id=? AND project_id=? AND audit_id=?",
                (audit.organization_id, audit.project_id or "", audit.audit_id),
            ).fetchone()
            if expected_version is not None and (
                existing is None or existing["version"] != expected_version
            ):
                raise ValueError("Causal audit version conflict.")
            if existing is not None and existing["status"] in {
                "SUCCEEDED",
                "FAILED",
                "CANCELLED",
            }:
                raise ValueError("Completed causal audits are immutable.")
            connection.execute(
                """INSERT INTO causal_audit (audit_id, organization_id, project_id, execution_id, agent_id, status, classification, evaluator_ref, request_fingerprint, created_at, completed_at, version, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(organization_id, project_id, audit_id) DO UPDATE SET status=excluded.status, classification=excluded.classification, completed_at=excluded.completed_at, version=excluded.version, payload_json=excluded.payload_json""",
                (
                    audit.audit_id,
                    audit.organization_id,
                    audit.project_id or "",
                    audit.execution_id,
                    audit.agent_id,
                    audit.status.value,
                    audit.classification.value if audit.classification else None,
                    audit.evaluator_ref,
                    audit.request_fingerprint,
                    audit.created_at.isoformat(),
                    audit.completed_at.isoformat() if audit.completed_at else None,
                    audit.version,
                    payload,
                ),
            )
            connection.commit()
        return audit

    def get(
        self, audit_id: str, organization_id: str, project_id: str | None = None
    ) -> CausalAudit | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM causal_audit WHERE audit_id=? AND organization_id=? AND project_id=?",
                (audit_id, organization_id, project_id or ""),
            ).fetchone()
        return audit_from_payload(json.loads(row["payload_json"])) if row else None

    def find_by_fingerprint(
        self, fingerprint: str, organization_id: str, project_id: str | None = None
    ) -> CausalAudit | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM causal_audit WHERE request_fingerprint=? AND organization_id=? AND project_id=?",
                (fingerprint, organization_id, project_id or ""),
            ).fetchone()
        return audit_from_payload(json.loads(row["payload_json"])) if row else None

    def list(
        self,
        filters: CausalAuditListFilters,
        organization_id: str,
        project_id: str | None = None,
        execution_id: str | None = None,
    ) -> list[CausalAudit]:
        clauses, params = (
            ["organization_id=?", "project_id=?"],
            [organization_id, project_id or ""],
        )
        for column, value in (
            ("execution_id", execution_id),
            ("agent_id", filters.agent_id),
            (
                "classification",
                filters.classification.value if filters.classification else None,
            ),
            ("status", filters.status.value if filters.status else None),
            ("evaluator_ref", filters.evaluator_ref),
        ):
            if value is not None:
                clauses.append(f"{column}=?")
                params.append(value)
        if filters.created_after:
            clauses.append("created_at>=?")
            params.append(filters.created_after.isoformat())
        if filters.created_before:
            clauses.append("created_at<=?")
            params.append(filters.created_before.isoformat())
        params.extend([filters.limit, filters.offset])
        with self._database.connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM causal_audit WHERE {' AND '.join(clauses)} ORDER BY created_at DESC, audit_id DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [audit_from_payload(json.loads(row["payload_json"])) for row in rows]
