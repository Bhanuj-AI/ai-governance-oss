from __future__ import annotations

import json

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.evidence_fidelity import EvidenceFidelityComparison
from ai_governance.repositories.evidence_fidelity_persistence import (
    comparison_from_payload,
    comparison_to_payload,
)
from ai_governance.repositories.evidence_fidelity_repository import (
    EvidenceFidelityComparisonRepository,
)


class PostgresEvidenceFidelityComparisonRepository(EvidenceFidelityComparisonRepository):
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, comparison: EvidenceFidelityComparison) -> EvidenceFidelityComparison:
        payload = json.dumps(comparison_to_payload(comparison), sort_keys=True, separators=(",", ":"))
        with self._database.connect() as connection:
            existing = connection.execute("SELECT payload_json FROM evidence_fidelity_comparison WHERE organization_id=%s AND project_id=%s AND comparison_id=%s FOR UPDATE", (comparison.organization_id, comparison.project_id or "", comparison.comparison_id)).fetchone()
            if existing is not None:
                existing_payload = existing["payload_json"] if isinstance(existing["payload_json"], dict) else json.loads(existing["payload_json"])
                if existing_payload != json.loads(payload):
                    raise ValueError("Evidence-fidelity comparisons are immutable.")
                return comparison
            connection.execute("INSERT INTO evidence_fidelity_comparison (comparison_id, organization_id, project_id, source_execution_id, request_fingerprint, status, created_at, payload_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)", (comparison.comparison_id, comparison.organization_id, comparison.project_id or "", comparison.source_execution_id, comparison.request_fingerprint, comparison.status.value, comparison.created_at, payload))
            connection.commit()
        return comparison

    def get(self, comparison_id: str, organization_id: str, project_id: str | None = None) -> EvidenceFidelityComparison | None:
        return self._one("SELECT payload_json FROM evidence_fidelity_comparison WHERE comparison_id=%s AND organization_id=%s AND project_id=%s", (comparison_id, organization_id, project_id or ""))

    def find_by_fingerprint(self, fingerprint: str, organization_id: str, project_id: str | None = None) -> EvidenceFidelityComparison | None:
        return self._one("SELECT payload_json FROM evidence_fidelity_comparison WHERE request_fingerprint=%s AND organization_id=%s AND project_id=%s", (fingerprint, organization_id, project_id or ""))

    def list_for_execution(self, execution_id: str, organization_id: str, project_id: str | None = None) -> list[EvidenceFidelityComparison]:
        with self._database.connect() as connection:
            rows = connection.execute("SELECT payload_json FROM evidence_fidelity_comparison WHERE source_execution_id=%s AND organization_id=%s AND project_id=%s ORDER BY created_at DESC, comparison_id DESC", (execution_id, organization_id, project_id or "")).fetchall()
        return [self._decode(row["payload_json"]) for row in rows]

    def _one(self, query: str, params: tuple[str, ...]) -> EvidenceFidelityComparison | None:
        with self._database.connect() as connection:
            row = connection.execute(query, params).fetchone()
        return self._decode(row["payload_json"]) if row else None

    @staticmethod
    def _decode(payload: object) -> EvidenceFidelityComparison:
        return comparison_from_payload(payload if isinstance(payload, dict) else json.loads(str(payload)))
