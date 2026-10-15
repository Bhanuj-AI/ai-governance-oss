"""Persistence contract for immutable runtime-action delegations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ai_governance.runtime_authorization.delegation import RuntimeActionDelegation


class RuntimeActionDelegationRepositoryConflictError(ValueError):
    """Immutable delegation identity or idempotency was reused differently."""


class RuntimeActionDelegationRepository(ABC):
    """Tenant-scoped store that never overwrites delegation content."""

    @abstractmethod
    def save(self, delegation: RuntimeActionDelegation) -> RuntimeActionDelegation:
        """Persist a new delegation or return the identical idempotent grant.

        A caller that reuses an identifier or idempotency key with different
        immutable content must receive a conflict from the implementation.
        """

    @abstractmethod
    def get(
        self,
        delegation_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeActionDelegation | None:
        """Resolve one delegation inside the caller's established tenant scope."""

    @abstractmethod
    def find_by_idempotency_key(
        self,
        idempotency_key: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeActionDelegation | None:
        """Resolve a prior immutable issuance request in the tenant scope."""

    @abstractmethod
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
        """Record immutable revocation evidence without altering grant content."""
