"""SQLite persistence for immutable runtime-action delegations."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.repositories.runtime_action_delegation_repository import (
    RuntimeActionDelegationRepository,
    RuntimeActionDelegationRepositoryConflictError,
)
from ai_governance.runtime_authorization.delegation import (
    RuntimeActionDelegation,
    RuntimeActionDelegationPermission,
    RuntimeActionDelegationStatus,
)


@final
class SQLiteRuntimeActionDelegationRepository(RuntimeActionDelegationRepository):
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, delegation: RuntimeActionDelegation) -> RuntimeActionDelegation:
        with self._database.connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO runtime_action_delegation (
                        delegation_id, organization_id, project_id, version,
                        execution_id, issuer_id, runtime_actor_id, permissions_json,
                        issued_at, expires_at, contract_digest, idempotency_key,
                        status, revoked_at, revoked_by, revocation_reference,
                        schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _row_values(delegation),
                )
                connection.commit()
                return delegation
            except Exception as exc:
                if "unique" not in str(exc).lower():
                    raise
                existing = self._find_identity_or_idempotency(connection, delegation)
                if existing == delegation:
                    return existing
                raise RuntimeActionDelegationRepositoryConflictError(
                    "Delegation identity or idempotency key was reused with different content."
                ) from exc

    def get(
        self, delegation_id: str, organization_id: str, project_id: str | None = None
    ) -> RuntimeActionDelegation | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM runtime_action_delegation
                WHERE delegation_id=? AND organization_id=? AND project_id=?""",
                (delegation_id, organization_id, project_id or ""),
            ).fetchone()
        return _from_row(dict(row)) if row is not None else None

    def find_by_idempotency_key(
        self, idempotency_key: str, organization_id: str, project_id: str | None = None
    ) -> RuntimeActionDelegation | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM runtime_action_delegation
                WHERE idempotency_key=? AND organization_id=? AND project_id=?""",
                (idempotency_key, organization_id, project_id or ""),
            ).fetchone()
        return _from_row(dict(row)) if row is not None else None

    def revoke(
        self,
        delegation_id: str,
        organization_id: str,
        project_id: str | None,
        *,
        revoked_at: datetime,
        revoked_by: str,
        revocation_reference: str | None,
    ) -> RuntimeActionDelegation:
        existing = self.get(delegation_id, organization_id, project_id)
        if existing is None:
            raise KeyError("Delegation does not exist in the resolved tenant scope.")
        if existing.status is RuntimeActionDelegationStatus.REVOKED:
            return existing
        revoked = replace(
            existing,
            status=RuntimeActionDelegationStatus.REVOKED,
            revoked_at=revoked_at,
            revoked_by=revoked_by,
            revocation_reference=revocation_reference,
        )
        with self._database.connect() as connection:
            cursor = connection.execute(
                """UPDATE runtime_action_delegation
                SET status=?, revoked_at=?, revoked_by=?, revocation_reference=?
                WHERE delegation_id=? AND organization_id=? AND project_id=? AND status='ACTIVE'""",
                (
                    revoked.status.value,
                    revoked.revoked_at.isoformat(),
                    revoked.revoked_by,
                    revoked.revocation_reference,
                    delegation_id,
                    organization_id,
                    project_id or "",
                ),
            )
            connection.commit()
        if cursor.rowcount == 0:
            current = self.get(delegation_id, organization_id, project_id)
            if (
                current is not None
                and current.status is RuntimeActionDelegationStatus.REVOKED
            ):
                return current
            raise KeyError("Delegation does not exist in the resolved tenant scope.")
        return revoked

    @staticmethod
    def _find_identity_or_idempotency(connection, delegation: RuntimeActionDelegation):
        row = connection.execute(
            """SELECT * FROM runtime_action_delegation WHERE organization_id=? AND project_id=?
            AND (delegation_id=? OR idempotency_key=?) LIMIT 1""",
            (
                delegation.organization_id,
                delegation.project_id,
                delegation.delegation_id,
                delegation.idempotency_key,
            ),
        ).fetchone()
        return _from_row(dict(row)) if row is not None else None


def _row_values(delegation: RuntimeActionDelegation) -> tuple[object, ...]:
    return (
        delegation.delegation_id,
        delegation.organization_id,
        delegation.project_id,
        delegation.version,
        delegation.execution_id,
        delegation.issuer_id,
        delegation.runtime_actor_id,
        json.dumps(
            [
                {
                    "action_id": permission.action_id,
                    "resource_type": permission.resource_type,
                    "resource_references": list(permission.resource_references),
                }
                for permission in delegation.permissions
            ],
            sort_keys=True,
            separators=(",", ":"),
        ),
        delegation.issued_at.isoformat(),
        delegation.expires_at.isoformat(),
        delegation.contract_digest,
        delegation.idempotency_key,
        delegation.status.value,
        delegation.revoked_at.isoformat() if delegation.revoked_at else None,
        delegation.revoked_by,
        delegation.revocation_reference,
        delegation.schema_version,
    )


def _from_row(row: dict[str, object]) -> RuntimeActionDelegation:
    permissions_raw = json.loads(str(row["permissions_json"]))
    permissions = tuple(
        RuntimeActionDelegationPermission(
            action_id=str(value["action_id"]),
            resource_type=str(value["resource_type"]),
            resource_references=tuple(
                str(item) for item in value["resource_references"]
            ),
        )
        for value in permissions_raw
    )
    return RuntimeActionDelegation(
        delegation_id=str(row["delegation_id"]),
        version=str(row["version"]),
        organization_id=str(row["organization_id"]),
        project_id=str(row["project_id"]),
        execution_id=str(row["execution_id"]),
        issuer_id=str(row["issuer_id"]),
        runtime_actor_id=str(row["runtime_actor_id"]),
        permissions=permissions,
        issued_at=datetime.fromisoformat(str(row["issued_at"])),
        expires_at=datetime.fromisoformat(str(row["expires_at"])),
        contract_digest=str(row["contract_digest"]),
        idempotency_key=str(row["idempotency_key"]),
        status=str(row["status"]),
        revoked_at=(
            datetime.fromisoformat(str(row["revoked_at"]))
            if row["revoked_at"] is not None
            else None
        ),
        revoked_by=str(row["revoked_by"]) if row["revoked_by"] is not None else None,
        revocation_reference=(
            str(row["revocation_reference"])
            if row["revocation_reference"] is not None
            else None
        ),
        schema_version=str(row["schema_version"]),
    )
