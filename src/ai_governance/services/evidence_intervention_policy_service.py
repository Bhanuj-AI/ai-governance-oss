from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ai_governance.domain.causal_audit import (
    EvidenceInterventionPolicy,
    EvidenceInterventionPolicyStatus,
    ToolEvidenceDescriptor,
)
from ai_governance.domain.replay import ControlledEvidenceStrategy
from ai_governance.services.evidence_interventions import (
    EvidenceInterventionProviderRegistry,
)
from ai_governance.tenancy.domain import TenantContext


class InterventionPolicyNotFound(ValueError):
    code = "INTERVENTION_POLICY_NOT_CONFIGURED"


class InterventionPolicyInactive(ValueError):
    code = "INTERVENTION_POLICY_INACTIVE"


class InterventionPolicyAmbiguous(ValueError):
    code = "AMBIGUOUS_INTERVENTION_POLICY"


class EvidenceInterventionPolicyService:
    def __init__(
        self,
        repository,
        providers: EvidenceInterventionProviderRegistry,
        clock=None,
        id_generator=None,
    ) -> None:
        self._repository, self._providers = repository, providers
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ids = id_generator or (lambda: uuid4().hex)

    def create_draft(
        self,
        *,
        tool_name: str,
        schema_id: str,
        schema_version: str,
        provider_id: str,
        provider_version: str,
        allowed_strategies: tuple[ControlledEvidenceStrategy, ...],
        strategy_configuration: dict,
        context: TenantContext,
    ) -> EvidenceInterventionPolicy:
        policy = EvidenceInterventionPolicy(
            self._ids(),
            1,
            context.organization_id,
            context.project_id,
            EvidenceInterventionPolicyStatus.DRAFT,
            tool_name,
            schema_id,
            schema_version,
            provider_id,
            provider_version,
            allowed_strategies,
            strategy_configuration,
            self._clock(),
            context.actor_id,
        )
        return self._repository.save(policy)

    def create_next_draft(
        self,
        policy_id: str,
        version: int,
        strategy_configuration: dict,
        context: TenantContext,
    ) -> EvidenceInterventionPolicy:
        """Edit an active policy by creating, never mutating, its next version."""
        current = self.get(policy_id, version, context)
        return self._repository.save(
            current.next_draft(context.actor_id, self._clock(), strategy_configuration)
        )

    def get(
        self, policy_id: str, version: int, context: TenantContext
    ) -> EvidenceInterventionPolicy:
        policy = self._repository.get(
            policy_id, version, context.organization_id, context.project_id
        )
        if policy is None:
            raise InterventionPolicyNotFound("INTERVENTION_POLICY_NOT_CONFIGURED")
        return policy

    def list(self, context: TenantContext) -> list[EvidenceInterventionPolicy]:
        return self._repository.list(context.organization_id, context.project_id)

    def list_versions(
        self, policy_id: str, context: TenantContext
    ) -> list[EvidenceInterventionPolicy]:
        policies = [item for item in self.list(context) if item.policy_id == policy_id]
        if not policies:
            raise InterventionPolicyNotFound("INTERVENTION_POLICY_NOT_CONFIGURED")
        return policies

    def validate(
        self, policy_id: str, version: int, context: TenantContext
    ) -> EvidenceInterventionPolicy:
        policy = self.get(policy_id, version, context)
        self._providers.resolve(policy).validate_policy(policy, context)
        return policy

    def activate(
        self, policy_id: str, version: int, context: TenantContext
    ) -> EvidenceInterventionPolicy:
        policy = self.validate(policy_id, version, context)
        active = [
            item
            for item in self._repository.list(
                context.organization_id, context.project_id
            )
            if item.status is EvidenceInterventionPolicyStatus.ACTIVE
            and item.tool_name == policy.tool_name
            and item.schema_id == policy.schema_id
            and item.schema_version == policy.schema_version
            and (item.policy_id != policy.policy_id or item.version != policy.version)
        ]
        if active:
            raise InterventionPolicyAmbiguous("AMBIGUOUS_INTERVENTION_POLICY")
        return self._repository.save(policy.activate(context.actor_id, self._clock()))

    def retire(
        self, policy_id: str, version: int, context: TenantContext
    ) -> EvidenceInterventionPolicy:
        return self._repository.save(
            self.get(policy_id, version, context).retire(self._clock())
        )

    def resolve_active(
        self,
        descriptor: ToolEvidenceDescriptor,
        strategy: ControlledEvidenceStrategy,
        context: TenantContext,
    ) -> EvidenceInterventionPolicy:
        matches = [
            item
            for item in self._repository.list(
                context.organization_id, context.project_id
            )
            if item.status is EvidenceInterventionPolicyStatus.ACTIVE
            and item.tool_name == descriptor.tool_name
            and item.schema_id == descriptor.schema_id
            and item.schema_version == descriptor.schema_version
            and strategy in item.allowed_strategies
        ]
        if not matches:
            raise InterventionPolicyInactive("INTERVENTION_POLICY_INACTIVE")
        if len(matches) > 1:
            raise InterventionPolicyAmbiguous("AMBIGUOUS_INTERVENTION_POLICY")
        return matches[0]
