from __future__ import annotations

import json

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.evidence_fidelity import EvidenceFidelityComparison
from ai_governance.repositories.evidence_fidelity_persistence import (
    comparison_from_payload,
    comparison_to_payload,
)
from ai_governance.repositories.evidence_fidelity_repository import (
    EvidenceFidelityComparisonRepository,
)


class SQLiteEvidenceFidelityComparisonRepository(EvidenceFidelityComparisonRepository):
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, comparison: EvidenceFidelityComparison) -> EvidenceFidelityComparison:
        payload = json.dumps(comparison_to_payload(comparison), sort_keys=True, separators=(",", ":"))
        with self._database.connect() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM evidence_fidelity_comparison WHERE organization_id=? AND project_id=? AND comparison_id=?",
                (comparison.organization_id, comparison.project_id or "", comparison.comparison_id),
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] != payload:
                    raise ValueError("Evidence-fidelity comparisons are immutable.")
                return comparison
            duplicate = connection.execute(
                "SELECT comparison_id FROM evidence_fidelity_comparison WHERE organization_id=? AND project_id=? AND request_fingerprint=?",
                (comparison.organization_id, comparison.project_id or "", comparison.request_fingerprint),
            ).fetchone()
            if duplicate is not None:
                raise ValueError("Evidence-fidelity request fingerprint already exists.")
            connection.execute(
                "INSERT INTO evidence_fidelity_comparison (comparison_id, organization_id, project_id, source_execution_id, request_fingerprint, status, created_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (comparison.comparison_id, comparison.organization_id, comparison.project_id or "", comparison.source_execution_id, comparison.request_fingerprint, comparison.status.value, comparison.created_at.isoformat(), payload),
            )
            connection.commit()
        return comparison

    def get(self, comparison_id: str, organization_id: str, project_id: str | None = None) -> EvidenceFidelityComparison | None:
        return self._one("SELECT payload_json FROM evidence_fidelity_comparison WHERE comparison_id=? AND organization_id=? AND project_id=?", (comparison_id, organization_id, project_id or ""))

    def find_by_fingerprint(self, fingerprint: str, organization_id: str, project_id: str | None = None) -> EvidenceFidelityComparison | None:
        return self._one("SELECT payload_json FROM evidence_fidelity_comparison WHERE request_fingerprint=? AND organization_id=? AND project_id=?", (fingerprint, organization_id, project_id or ""))

    def list_for_execution(self, execution_id: str, organization_id: str, project_id: str | None = None) -> list[EvidenceFidelityComparison]:
        with self._database.connect() as connection:
            rows = connection.execute("SELECT payload_json FROM evidence_fidelity_comparison WHERE source_execution_id=? AND organization_id=? AND project_id=? ORDER BY created_at DESC, comparison_id DESC", (execution_id, organization_id, project_id or "")).fetchall()
        return [comparison_from_payload(json.loads(row["payload_json"])) for row in rows]

    def _one(self, query: str, params: tuple[str, ...]) -> EvidenceFidelityComparison | None:
        with self._database.connect() as connection:
            row = connection.execute(query, params).fetchone()
        return comparison_from_payload(json.loads(row["payload_json"])) if row else None
