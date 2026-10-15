"""Issuer-side registration and revocation of trusted runtime delegations."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from ai_governance.decisions import (
    DecisionTargetType,
    GovernancePolicyEvaluator,
    PolicyEffect,
    PolicyEvaluationContext,
    PolicyStatus,
)
from ai_governance.repositories.agent_execution_repository import (
    AgentExecutionRepository,
)
from ai_governance.repositories.policy_administration_repository import (
    PolicyAdministrationRepository,
)
from ai_governance.repositories.runtime_action_delegation_repository import (
    RuntimeActionDelegationRepository,
    RuntimeActionDelegationRepositoryConflictError,
)
from ai_governance.runtime_authorization.delegation import (
    RuntimeActionDelegation,
    RuntimeActionDelegationPermission,
    create_runtime_action_delegation,
)
from ai_governance.tenancy.domain import TenantContext

RUNTIME_ACTION_DELEGATION_ISSUANCE_METADATA_KEY = "runtime_action_delegation_issuance"
RUNTIME_ACTION_DELEGATION_ISSUANCE_PURPOSE = "runtime_action_delegation_issuance"


class RuntimeActionDelegationError(Exception):
    """Base exception for trusted delegation registration."""


class RuntimeActionDelegationNotFoundError(RuntimeActionDelegationError):
    """A referenced execution or delegation is absent from the tenant scope."""


class RuntimeActionDelegationDeniedError(RuntimeActionDelegationError):
    """The issuer lacks an active server-side policy grant for the request."""


class RuntimeActionDelegationConflictError(RuntimeActionDelegationError):
    """Immutable delegation identity or idempotency was changed."""


class RuntimeActionDelegationRegistration:
    """Input from a separately authorized issuer; issuer identity is not supplied."""

    def __init__(
        self,
        *,
        execution_id: str,
        runtime_actor_id: str,
        permissions: Sequence[RuntimeActionDelegationPermission],
        expires_at: datetime,
        idempotency_key: str,
    ) -> None:
        self.execution_id = execution_id
        self.runtime_actor_id = runtime_actor_id
        self.permissions = tuple(permissions)
        self.expires_at = expires_at
        self.idempotency_key = idempotency_key


class RuntimeActionDelegationService:
    """Issue grants only after trusted tenant, execution, and policy checks."""

    def __init__(
        self,
        *,
        repository: RuntimeActionDelegationRepository,
        execution_repository: AgentExecutionRepository,
        policy_repository: PolicyAdministrationRepository,
        clock: Callable[[], datetime] | None = None,
        id_generator: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._execution_repository = execution_repository
        self._policy_repository = policy_repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._evaluator = GovernancePolicyEvaluator()

    def register(
        self,
        registration: RuntimeActionDelegationRegistration,
        context: TenantContext,
    ) -> RuntimeActionDelegation:
        execution = self._execution_repository.get(
            registration.execution_id, context.organization_id, context.project_id
        )
        if execution is None:
            raise RuntimeActionDelegationNotFoundError(
                "Execution does not exist in the resolved tenant scope."
            )
        existing = self._repository.find_by_idempotency_key(
            registration.idempotency_key,
            context.organization_id,
            context.project_id,
        )
        if existing is not None:
            if _matches_registration(existing, registration, context):
                return existing
            raise RuntimeActionDelegationConflictError(
                "Delegation idempotency key was reused with different content."
            )
        now = self._clock()
        if registration.expires_at.tzinfo is None or registration.expires_at <= now:
            raise RuntimeActionDelegationDeniedError(
                "Delegation expiry must be in the future."
            )
        if not registration.permissions:
            raise RuntimeActionDelegationDeniedError(
                "Delegation must include an explicit permission."
            )
        for permission in registration.permissions:
            if not self._issuer_permitted(
                permission, registration.runtime_actor_id, context
            ):
                raise RuntimeActionDelegationDeniedError(
                    "Issuer is not permitted to grant the requested runtime action scope."
                )
        delegation = create_runtime_action_delegation(
            delegation_id=self._id_generator(),
            organization_id=context.organization_id,
            project_id=context.project_id,
            execution_id=registration.execution_id,
            issuer_id=context.actor_id,
            runtime_actor_id=registration.runtime_actor_id,
            permissions=registration.permissions,
            issued_at=now,
            expires_at=registration.expires_at,
            idempotency_key=registration.idempotency_key,
        )
        try:
            return self._repository.save(delegation)
        except RuntimeActionDelegationRepositoryConflictError as exc:
            raise RuntimeActionDelegationConflictError(str(exc)) from exc

    def revoke(
        self,
        delegation_id: str,
        *,
        revocation_reference: str | None,
        context: TenantContext,
    ) -> RuntimeActionDelegation:
        try:
            return self._repository.revoke(
                delegation_id,
                context.organization_id,
                context.project_id,
                revoked_at=self._clock(),
                revoked_by=context.actor_id,
                revocation_reference=revocation_reference,
            )
        except KeyError as exc:
            raise RuntimeActionDelegationNotFoundError(str(exc)) from exc

    def _issuer_permitted(
        self,
        permission: RuntimeActionDelegationPermission,
        runtime_actor_id: str,
        context: TenantContext,
    ) -> bool:
        candidates = []
        for definition in self._policy_repository.list_definitions(
            organization_id=context.organization_id,
            project_id=context.project_id,
            status=PolicyStatus.ACTIVE,
        ):
            metadata = definition.metadata.get(
                RUNTIME_ACTION_DELEGATION_ISSUANCE_METADATA_KEY
            )
            if (
                not isinstance(metadata, Mapping)
                or metadata.get("purpose") != RUNTIME_ACTION_DELEGATION_ISSUANCE_PURPOSE
            ):
                continue
            version = self._policy_repository.get_active_version(definition.policy_id)
            if (
                version is None
                or DecisionTargetType.AGENT_EXECUTION not in version.target_types
            ):
                continue
            candidates.append((definition, version))

        for reference in permission.resource_references:
            matched_allow = False
            for definition, version in candidates:
                outcome = self._evaluator.evaluate_with_trace(
                    version.to_governance_policy(definition),
                    PolicyEvaluationContext(
                        target_type=DecisionTargetType.AGENT_EXECUTION,
                        target_id="runtime-action-delegation-issuance",
                        evidence={
                            "issuer": {"id": context.actor_id},
                            "runtime_actor": {"id": runtime_actor_id},
                            "action": {"id": permission.action_id},
                            "resource": {
                                "type": permission.resource_type,
                                "reference": reference,
                            },
                        },
                    ),
                ).outcome
                if not outcome.matched:
                    continue
                if outcome.effect in {PolicyEffect.REJECT, PolicyEffect.BLOCK}:
                    return False
                if outcome.effect is PolicyEffect.APPROVE:
                    matched_allow = True
                else:
                    return False
            if not matched_allow:
                return False
        return True


def _matches_registration(
    delegation: RuntimeActionDelegation,
    registration: RuntimeActionDelegationRegistration,
    context: TenantContext,
) -> bool:
    return (
        delegation.execution_id == registration.execution_id
        and delegation.issuer_id == context.actor_id
        and delegation.runtime_actor_id == registration.runtime_actor_id
        and delegation.permissions == registration.permissions
        and delegation.expires_at == registration.expires_at
    )
