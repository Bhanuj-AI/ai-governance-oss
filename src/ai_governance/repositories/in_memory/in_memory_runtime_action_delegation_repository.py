"""In-memory immutable runtime-action delegation persistence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from threading import Lock

from ai_governance.repositories.runtime_action_delegation_repository import (
    RuntimeActionDelegationRepository,
    RuntimeActionDelegationRepositoryConflictError,
)
from ai_governance.runtime_authorization.delegation import (
    RuntimeActionDelegation,
    RuntimeActionDelegationStatus,
)


class InMemoryRuntimeActionDelegationRepository(RuntimeActionDelegationRepository):
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], RuntimeActionDelegation] = {}
        self._by_idempotency: dict[tuple[str, str, str], RuntimeActionDelegation] = {}
        self._lock = Lock()

    def save(self, delegation: RuntimeActionDelegation) -> RuntimeActionDelegation:
        tenant = (delegation.organization_id, delegation.project_id)
        identity = (*tenant, delegation.delegation_id)
        idempotency = (*tenant, delegation.idempotency_key)
        with self._lock:
            existing = self._items.get(identity) or self._by_idempotency.get(
                idempotency
            )
            if existing is not None:
                if existing == delegation:
                    return existing
                raise RuntimeActionDelegationRepositoryConflictError(
                    "Delegation identity or idempotency key was reused with different content."
                )
            self._items[identity] = delegation
            self._by_idempotency[idempotency] = delegation
            return delegation

    def get(
        self, delegation_id: str, organization_id: str, project_id: str | None = None
    ) -> RuntimeActionDelegation | None:
        return self._items.get((organization_id, project_id or "", delegation_id))

    def find_by_idempotency_key(
        self, idempotency_key: str, organization_id: str, project_id: str | None = None
    ) -> RuntimeActionDelegation | None:
        return self._by_idempotency.get(
            (organization_id, project_id or "", idempotency_key)
        )

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
        identity = (organization_id, project_id or "", delegation_id)
        with self._lock:
            existing = self._items.get(identity)
            if existing is None:
                raise KeyError(
                    "Delegation does not exist in the resolved tenant scope."
                )
            if existing.status is RuntimeActionDelegationStatus.REVOKED:
                return existing
            revoked = replace(
                existing,
                status=RuntimeActionDelegationStatus.REVOKED,
                revoked_at=revoked_at,
                revoked_by=revoked_by,
                revocation_reference=revocation_reference,
            )
            self._items[identity] = revoked
            self._by_idempotency[
                (organization_id, project_id or "", existing.idempotency_key)
            ] = revoked
            return revoked
