from __future__ import annotations

import json

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.causal_audit import CausalAudit
from ai_governance.repositories.causal_audit_persistence import (
    audit_from_payload,
    audit_to_payload,
)
from ai_governance.repositories.causal_audit_repository import (
    CausalAuditListFilters,
    CausalAuditRepository,
)


class PostgresCausalAuditRepository(CausalAuditRepository):
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(
        self, audit: CausalAudit, expected_version: int | None = None
    ) -> CausalAudit:
        payload = json.dumps(
            audit_to_payload(audit), sort_keys=True, separators=(",", ":")
        )
        with self._database.connect() as connection:
            existing = connection.execute(
                "SELECT version, status FROM causal_audit WHERE organization_id=%s AND project_id=%s AND audit_id=%s FOR UPDATE",
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
                """INSERT INTO causal_audit (audit_id, organization_id, project_id, execution_id, agent_id, status, classification, evaluator_ref, request_fingerprint, created_at, completed_at, version, payload_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT(organization_id, project_id, audit_id) DO UPDATE SET status=excluded.status, classification=excluded.classification, completed_at=excluded.completed_at, version=excluded.version, payload_json=excluded.payload_json""",
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
                    audit.created_at,
                    audit.completed_at,
                    audit.version,
                    payload,
                ),
            )
            connection.commit()
        return audit

    def get(
        self, audit_id: str, organization_id: str, project_id: str | None = None
    ) -> CausalAudit | None:
        return self._one(
            "SELECT payload_json FROM causal_audit WHERE audit_id=%s AND organization_id=%s AND project_id=%s",
            (audit_id, organization_id, project_id or ""),
        )

    def find_by_fingerprint(
        self, fingerprint: str, organization_id: str, project_id: str | None = None
    ) -> CausalAudit | None:
        return self._one(
            "SELECT payload_json FROM causal_audit WHERE request_fingerprint=%s AND organization_id=%s AND project_id=%s",
            (fingerprint, organization_id, project_id or ""),
        )

    def list(
        self,
        filters: CausalAuditListFilters,
        organization_id: str,
        project_id: str | None = None,
        execution_id: str | None = None,
    ) -> list[CausalAudit]:
        clauses, params = (
            ["organization_id=%s", "project_id=%s"],
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
                clauses.append(f"{column}=%s")
                params.append(value)
        if filters.created_after:
            clauses.append("created_at>=%s")
            params.append(filters.created_after)
        if filters.created_before:
            clauses.append("created_at<=%s")
            params.append(filters.created_before)
        params.extend([filters.limit, filters.offset])
        with self._database.connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM causal_audit WHERE {' AND '.join(clauses)} ORDER BY created_at DESC, audit_id DESC LIMIT %s OFFSET %s",
                params,
            ).fetchall()
        return [
            audit_from_payload(
                row["payload_json"]
                if isinstance(row["payload_json"], dict)
                else json.loads(row["payload_json"])
            )
            for row in rows
        ]

    def _one(self, query: str, params) -> CausalAudit | None:
        with self._database.connect() as connection:
            row = connection.execute(query, params).fetchone()
        if row is None:
            return None
        payload = row["payload_json"]
        return audit_from_payload(
            payload if isinstance(payload, dict) else json.loads(payload)
        )
