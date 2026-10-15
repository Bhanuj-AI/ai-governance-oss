"""PostgreSQL persistence for immutable runtime-action delegations."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
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
class PostgresRuntimeActionDelegationRepository(RuntimeActionDelegationRepository):
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, delegation: RuntimeActionDelegation) -> RuntimeActionDelegation:
        with self._database.connect() as connection:
            try:
                connection.execute(
                    """INSERT INTO runtime_action_delegation (
                        delegation_id, organization_id, project_id, version,
                        execution_id, issuer_id, runtime_actor_id, permissions_json,
                        issued_at, expires_at, contract_digest, idempotency_key,
                        status, revoked_at, revoked_by, revocation_reference, schema_version
                    ) VALUES (
                        %(delegation_id)s, %(organization_id)s, %(project_id)s, %(version)s,
                        %(execution_id)s, %(issuer_id)s, %(runtime_actor_id)s, %(permissions_json)s::jsonb,
                        %(issued_at)s, %(expires_at)s, %(contract_digest)s, %(idempotency_key)s,
                        %(status)s, %(revoked_at)s, %(revoked_by)s, %(revocation_reference)s, %(schema_version)s
                    )""",
                    _values(delegation),
                )
                connection.commit()
                return delegation
            except Exception as exc:
                if (
                    "unique" not in str(exc).lower()
                    and "duplicate" not in str(exc).lower()
                ):
                    raise
                existing = self._find_identity_or_idempotency(delegation)
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
                """SELECT * FROM runtime_action_delegation WHERE delegation_id=%(delegation_id)s
                AND organization_id=%(organization_id)s AND project_id=%(project_id)s""",
                {
                    "delegation_id": delegation_id,
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                },
            ).fetchone()
        return _from_row(row) if row is not None else None

    def find_by_idempotency_key(
        self, idempotency_key: str, organization_id: str, project_id: str | None = None
    ) -> RuntimeActionDelegation | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM runtime_action_delegation WHERE idempotency_key=%(idempotency_key)s
                AND organization_id=%(organization_id)s AND project_id=%(project_id)s""",
                {
                    "idempotency_key": idempotency_key,
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                },
            ).fetchone()
        return _from_row(row) if row is not None else None

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
            row = connection.execute(
                """UPDATE runtime_action_delegation SET status=%(status)s, revoked_at=%(revoked_at)s,
                revoked_by=%(revoked_by)s, revocation_reference=%(revocation_reference)s
                WHERE delegation_id=%(delegation_id)s AND organization_id=%(organization_id)s
                AND project_id=%(project_id)s AND status='ACTIVE' RETURNING *""",
                {**_values(revoked), "project_id": project_id or ""},
            ).fetchone()
            connection.commit()
        if row is not None:
            return _from_row(row)
        current = self.get(delegation_id, organization_id, project_id)
        if (
            current is not None
            and current.status is RuntimeActionDelegationStatus.REVOKED
        ):
            return current
        raise KeyError("Delegation does not exist in the resolved tenant scope.")

    def _find_identity_or_idempotency(
        self, delegation: RuntimeActionDelegation
    ) -> RuntimeActionDelegation | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM runtime_action_delegation WHERE organization_id=%(organization_id)s
                AND project_id=%(project_id)s AND (delegation_id=%(delegation_id)s OR idempotency_key=%(idempotency_key)s) LIMIT 1""",
                _values(delegation),
            ).fetchone()
        return _from_row(row) if row is not None else None


def _values(delegation: RuntimeActionDelegation) -> dict[str, object]:
    return {
        "delegation_id": delegation.delegation_id,
        "organization_id": delegation.organization_id,
        "project_id": delegation.project_id,
        "version": delegation.version,
        "execution_id": delegation.execution_id,
        "issuer_id": delegation.issuer_id,
        "runtime_actor_id": delegation.runtime_actor_id,
        "permissions_json": json.dumps(
            [
                {
                    "action_id": item.action_id,
                    "resource_type": item.resource_type,
                    "resource_references": list(item.resource_references),
                }
                for item in delegation.permissions
            ]
        ),
        "issued_at": delegation.issued_at,
        "expires_at": delegation.expires_at,
        "contract_digest": delegation.contract_digest,
        "idempotency_key": delegation.idempotency_key,
        "status": delegation.status.value,
        "revoked_at": delegation.revoked_at,
        "revoked_by": delegation.revoked_by,
        "revocation_reference": delegation.revocation_reference,
        "schema_version": delegation.schema_version,
    }


def _from_row(row: dict[str, object]) -> RuntimeActionDelegation:
    raw = row["permissions_json"]
    permissions_data = json.loads(raw) if isinstance(raw, str) else raw
    permissions = tuple(
        RuntimeActionDelegationPermission(
            action_id=str(item["action_id"]),
            resource_type=str(item["resource_type"]),
            resource_references=tuple(
                str(value) for value in item["resource_references"]
            ),
        )
        for item in permissions_data
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
        issued_at=row["issued_at"],
        expires_at=row["expires_at"],
        contract_digest=str(row["contract_digest"]),
        idempotency_key=str(row["idempotency_key"]),
        status=str(row["status"]),
        revoked_at=row["revoked_at"],
        revoked_by=row["revoked_by"],
        revocation_reference=row["revocation_reference"],
        schema_version=str(row["schema_version"]),
    )
