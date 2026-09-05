from __future__ import annotations

import json

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.causal_audit import EvidenceInterventionPolicy
from ai_governance.repositories.evidence_intervention_policy_persistence import (
    policy_from_payload,
    policy_to_payload,
)
from ai_governance.repositories.evidence_intervention_policy_repository import (
    EvidenceInterventionPolicyRepository,
)


class SQLiteEvidenceInterventionPolicyRepository(EvidenceInterventionPolicyRepository):
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, policy: EvidenceInterventionPolicy) -> EvidenceInterventionPolicy:
        payload = json.dumps(
            policy_to_payload(policy), sort_keys=True, separators=(",", ":")
        )
        with self._database.connect() as connection:
            current = connection.execute(
                "SELECT status, policy_digest FROM evidence_intervention_policy "
                "WHERE organization_id=? AND project_id=? AND policy_id=? AND version=?",
                (
                    policy.organization_id,
                    policy.project_id or "",
                    policy.policy_id,
                    policy.version,
                ),
            ).fetchone()
            if (
                current
                and current["status"] == "ACTIVE"
                and (
                    current["policy_digest"] != policy.policy_digest
                    or policy.status.value not in {"ACTIVE", "RETIRED"}
                )
            ):
                raise ValueError(
                    "InterventionPolicyConflict: active policy versions are immutable."
                )
            connection.execute(
                """INSERT INTO evidence_intervention_policy
                (policy_id, version, organization_id, project_id, status, tool_name, schema_id,
                 schema_version, provider_id, provider_version, policy_digest, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(organization_id, project_id, policy_id, version) DO UPDATE SET
                status=excluded.status, policy_digest=excluded.policy_digest, payload_json=excluded.payload_json""",
                (
                    policy.policy_id,
                    policy.version,
                    policy.organization_id,
                    policy.project_id or "",
                    policy.status.value,
                    policy.tool_name,
                    policy.schema_id,
                    policy.schema_version,
                    policy.provider_id,
                    policy.provider_version,
                    policy.policy_digest,
                    policy.created_at.isoformat(),
                    payload,
                ),
            )
            connection.commit()
        return policy

    def get(
        self, policy_id: str, version: int, organization_id: str, project_id: str | None
    ) -> EvidenceInterventionPolicy | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM evidence_intervention_policy "
                "WHERE policy_id=? AND version=? AND organization_id=? AND project_id=?",
                (policy_id, version, organization_id, project_id or ""),
            ).fetchone()
        return policy_from_payload(json.loads(row["payload_json"])) if row else None

    def list(
        self, organization_id: str, project_id: str | None
    ) -> list[EvidenceInterventionPolicy]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM evidence_intervention_policy "
                "WHERE organization_id=? AND project_id=? ORDER BY policy_id, version",
                (organization_id, project_id or ""),
            ).fetchall()
        return [policy_from_payload(json.loads(row["payload_json"])) for row in rows]
