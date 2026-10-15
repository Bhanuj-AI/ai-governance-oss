"""Deterministic, tenant-bound authorization for external runtime actions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from ai_governance.decisions import (
    DecisionTargetType,
    GovernancePolicyEvaluator,
    PolicyEffect,
    PolicyEvaluationContext,
    PolicyStatus,
)
from ai_governance.decisions.policy_administration import (
    PolicyDefinition,
    PolicyVersion,
)
from ai_governance.domain.agent_execution import (
    ActorType,
    AgentExecutionEvent,
    EventType,
)
from ai_governance.domain.agent_execution.errors import (
    AgentExecutionIdempotencyConflict,
)
from ai_governance.repositories.agent_execution_repository import (
    AgentExecutionEventRepository,
    AgentExecutionRepository,
)
from ai_governance.repositories.policy_administration_repository import (
    PolicyAdministrationRepository,
)
from ai_governance.repositories.runtime_action_delegation_repository import (
    RuntimeActionDelegationRepository,
)
from ai_governance.runtime_authorization import (
    RuntimeActionAuthorizationDecision,
    RuntimeActionAuthorizationOutcome,
    RuntimeActionAuthorizationRequest,
    RuntimeActionResource,
)
from ai_governance.runtime_authorization.delegation import RuntimeActionDelegation
from ai_governance.tenancy.domain import TenantContext

RUNTIME_ACTION_AUTHORIZATION_METADATA_KEY = "runtime_action_authorization"
RUNTIME_ACTION_AUTHORIZATION_PURPOSE = "runtime_action_authorization"
_EVENT_IDEMPOTENCY_PREFIX = "runtime-action-authorization:"


class RuntimeActionAuthorizationError(Exception):
    """Base error for runtime action authorization."""


class RuntimeActionAuthorizationNotFoundError(RuntimeActionAuthorizationError):
    """The referenced execution is absent from the resolved tenant scope."""


class RuntimeActionAuthorizationConflictError(RuntimeActionAuthorizationError):
    """An idempotency key was reused with different semantic input."""


class RuntimeActionAuthorizationPersistenceError(RuntimeActionAuthorizationError):
    """An otherwise-computed decision could not be recorded."""


class RuntimeActionAuthorizationService:
    """Evaluate active authorization policies and append decision evidence.

    Active policy definitions opt in with definition metadata of the form::

        {
            "runtime_action_authorization": {
                "purpose": "runtime_action_authorization",
                "registered_actions": ["claims.update"],
                "registered_resource_types": ["sqlite.row"],
            }
        }

    The policy's normal structured rules operate over ``action``, ``resource``,
    ``actor``, and ``context`` evidence. Existing ``APPROVE`` effects allow an
    operation; ``REJECT`` and ``BLOCK`` effects deny it. No new policy DSL or
    policy store is introduced.
    """

    def __init__(
        self,
        *,
        policy_repository: PolicyAdministrationRepository,
        execution_repository: AgentExecutionRepository,
        event_repository: AgentExecutionEventRepository,
        delegation_repository: RuntimeActionDelegationRepository | None = None,
        decision_ttl: timedelta = timedelta(minutes=5),
        clock: Callable[[], datetime] | None = None,
        id_generator: Callable[[], str] | None = None,
    ) -> None:
        if decision_ttl <= timedelta(0):
            raise ValueError("decision_ttl must be positive.")
        self._policy_repository = policy_repository
        self._execution_repository = execution_repository
        self._event_repository = event_repository
        self._delegation_repository = delegation_repository
        self._decision_ttl = decision_ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._policy_evaluator = GovernancePolicyEvaluator()

    def authorize(
        self,
        request: RuntimeActionAuthorizationRequest,
        context: TenantContext,
    ) -> RuntimeActionAuthorizationDecision:
        """Return a persisted ALLOW or DENY for exactly one operation."""

        execution = self._execution_repository.get(
            request.execution_id,
            context.organization_id,
            context.project_id,
        )
        if execution is None:
            raise RuntimeActionAuthorizationNotFoundError(
                "Execution does not exist in the resolved tenant scope."
            )

        correlation_id = self._resolve_correlation_id(request, context, execution)
        existing = self._event_repository.find_by_idempotency_key(
            self._event_idempotency_key(request.idempotency_key),
            request.execution_id,
            context.organization_id,
            context.project_id,
        )
        fingerprint = request.fingerprint()
        if existing is not None:
            return self._existing_decision(
                existing, request, context.actor_id, fingerprint
            )

        now = self._clock()
        decision = self._evaluate(
            request=request,
            context=context,
            correlation_id=correlation_id,
            now=now,
            request_fingerprint=fingerprint,
        )
        event = self._decision_event(decision, request, context, fingerprint)
        try:
            saved = self._event_repository.save(
                event,
                idempotency_key=self._event_idempotency_key(request.idempotency_key),
            )
        except AgentExecutionIdempotencyConflict as exc:
            existing = self._event_repository.find_by_idempotency_key(
                self._event_idempotency_key(request.idempotency_key),
                request.execution_id,
                context.organization_id,
                context.project_id,
            )
            if existing is not None:
                return self._existing_decision(
                    existing, request, context.actor_id, fingerprint
                )
            raise RuntimeActionAuthorizationConflictError(
                "Authorization idempotency key was reused with different input."
            ) from exc
        except Exception as exc:  # pragma: no cover - backend-specific failures
            raise RuntimeActionAuthorizationPersistenceError(
                "Authorization decision could not be persisted."
            ) from exc

        # A repository is permitted to return a prior event for an identical
        # concurrent request. Reconstruct it so the event remains authoritative.
        if saved.event_id != event.event_id:
            return self._existing_decision(
                saved, request, context.actor_id, fingerprint
            )
        return decision

    def _evaluate(
        self,
        *,
        request: RuntimeActionAuthorizationRequest,
        context: TenantContext,
        correlation_id: str | None,
        now: datetime,
        request_fingerprint: str,
    ) -> RuntimeActionAuthorizationDecision:
        if request.policy_id is not None or request.expected_policy_version is not None:
            return self._decision(
                request=request,
                context=context,
                correlation_id=correlation_id,
                now=now,
                request_fingerprint=request_fingerprint,
                outcome=RuntimeActionAuthorizationOutcome.DENY,
                reason_code="POLICY_SELECTION_NOT_ALLOWED",
            )

        delegation, delegation_error = self._resolve_delegation(request, context, now)
        if delegation_error is not None:
            return self._decision(
                request=request,
                context=context,
                correlation_id=correlation_id,
                now=now,
                request_fingerprint=request_fingerprint,
                outcome=RuntimeActionAuthorizationOutcome.DENY,
                reason_code=delegation_error,
            )

        try:
            selected, selection_error = self._select_policies(request, context)
        except Exception:  # noqa: BLE001 - policy-store faults must deny.
            return self._decision(
                request=request,
                context=context,
                correlation_id=correlation_id,
                now=now,
                request_fingerprint=request_fingerprint,
                outcome=RuntimeActionAuthorizationOutcome.DENY,
                reason_code="POLICY_EVALUATION_FAILED",
                delegation=delegation,
            )
        if selection_error is not None:
            return self._decision(
                request=request,
                context=context,
                correlation_id=correlation_id,
                now=now,
                request_fingerprint=request_fingerprint,
                outcome=RuntimeActionAuthorizationOutcome.DENY,
                reason_code=selection_error,
                delegation=delegation,
            )

        matched: list[
            tuple[int, str, PolicyDefinition, PolicyVersion, PolicyEffect]
        ] = []
        unsupported: tuple[PolicyDefinition, PolicyVersion] | None = None
        evidence = {
            "action": {"id": request.action_id},
            "resource": {
                "type": request.resource.resource_type,
                "reference": request.resource.resource_reference,
            },
            "actor": {"id": context.actor_id},
            "delegation": {
                "id": delegation.delegation_id,
                "version": delegation.version,
                "digest": delegation.contract_digest,
                "issuer_id": delegation.issuer_id,
                "runtime_actor_id": delegation.runtime_actor_id,
            },
            # Agent-provided facts are deliberately not exposed under policy
            # paths that can grant authority. They may only be used by a
            # rejecting/blocking rule as a further restriction.
            "agent_context": dict(request.context),
        }
        evaluated = tuple(
            (definition.policy_id, version.version) for definition, version in selected
        )
        for definition, version in selected:
            try:
                trace = self._policy_evaluator.evaluate_with_trace(
                    version.to_governance_policy(definition),
                    PolicyEvaluationContext(
                        target_type=DecisionTargetType.AGENT_EXECUTION,
                        target_id=request.execution_id,
                        evidence=evidence,
                    ),
                )
            except Exception:  # noqa: BLE001 - policy faults must deny.
                return self._decision(
                    request=request,
                    context=context,
                    correlation_id=correlation_id,
                    now=now,
                    request_fingerprint=request_fingerprint,
                    outcome=RuntimeActionAuthorizationOutcome.DENY,
                    reason_code="POLICY_EVALUATION_FAILED",
                    delegation=delegation,
                    evaluated_policies=evaluated,
                )
            outcome = trace.outcome
            if not outcome.matched:
                continue
            if outcome.effect not in {
                PolicyEffect.APPROVE,
                PolicyEffect.REJECT,
                PolicyEffect.BLOCK,
            }:
                unsupported = (definition, version)
                continue
            if (
                outcome.effect is PolicyEffect.APPROVE
                and _uses_agent_controlled_context(version)
            ):
                unsupported = (definition, version)
                continue
            matched.append(
                (
                    int(outcome.metadata.get("rule_priority", 0)),
                    definition.policy_id,
                    definition,
                    version,
                    outcome.effect,
                )
            )

        if unsupported is not None:
            definition, version = unsupported
            return self._decision(
                request=request,
                context=context,
                correlation_id=correlation_id,
                now=now,
                request_fingerprint=request_fingerprint,
                outcome=RuntimeActionAuthorizationOutcome.DENY,
                reason_code="UNSUPPORTED_AUTHORIZATION_POLICY_EFFECT",
                policy_id=definition.policy_id,
                policy_version=version.version,
                delegation=delegation,
                evaluated_policies=evaluated,
            )
        if not matched:
            return self._decision(
                request=request,
                context=context,
                correlation_id=correlation_id,
                now=now,
                request_fingerprint=request_fingerprint,
                outcome=RuntimeActionAuthorizationOutcome.DENY,
                reason_code="NO_APPLICABLE_POLICY",
                delegation=delegation,
                evaluated_policies=evaluated,
            )

        matched.sort(key=lambda item: (item[0], item[1]))
        denies = [
            item
            for item in matched
            if item[4] in {PolicyEffect.REJECT, PolicyEffect.BLOCK}
        ]
        selected_match = denies[0] if denies else matched[0]
        _, _, definition, version, _effect = selected_match
        return self._decision(
            request=request,
            context=context,
            correlation_id=correlation_id,
            now=now,
            request_fingerprint=request_fingerprint,
            outcome=(
                RuntimeActionAuthorizationOutcome.DENY
                if denies
                else RuntimeActionAuthorizationOutcome.ALLOW
            ),
            reason_code=(
                "DENY_OVERRIDES"
                if denies and len(matched) > 1
                else "DENY_POLICY_MATCHED"
                if denies
                else "ALLOW_POLICY_MATCHED"
            ),
            policy_id=definition.policy_id,
            policy_version=version.version,
            delegation=delegation,
            evaluated_policies=evaluated,
        )

    def _select_policies(
        self,
        request: RuntimeActionAuthorizationRequest,
        context: TenantContext,
    ) -> tuple[list[tuple[PolicyDefinition, PolicyVersion]], str | None]:
        candidate_definitions = []
        for definition in self._policy_repository.list_definitions(
            organization_id=context.organization_id,
            project_id=context.project_id,
            status=PolicyStatus.ACTIVE,
        ):
            version = self._policy_repository.get_active_version(definition.policy_id)
            if version is not None:
                candidate_definitions.append((definition, version))

        selected: list[tuple[PolicyDefinition, PolicyVersion]] = []
        action_registered = False
        resource_registered = False
        for definition, version in candidate_definitions:
            registration = self._registration(definition)
            if registration is None:
                continue
            actions = registration["registered_actions"]
            resource_types = registration["registered_resource_types"]
            action_registered = action_registered or request.action_id in actions
            resource_registered = (
                resource_registered or request.resource.resource_type in resource_types
            )
            if (
                request.action_id in actions
                and request.resource.resource_type in resource_types
                and DecisionTargetType.AGENT_EXECUTION in version.target_types
            ):
                selected.append((definition, version))

        if not selected:
            if not action_registered:
                return [], "UNSUPPORTED_ACTION"
            if not resource_registered:
                return [], "UNSUPPORTED_RESOURCE"
            return [], "NO_APPLICABLE_POLICY"
        return selected, None

    def _registration(
        self, definition: PolicyDefinition
    ) -> dict[str, tuple[str, ...]] | None:
        raw = definition.metadata.get(RUNTIME_ACTION_AUTHORIZATION_METADATA_KEY)
        if not isinstance(raw, Mapping):
            return None
        if raw.get("purpose") != RUNTIME_ACTION_AUTHORIZATION_PURPOSE:
            return None
        actions = _string_tuple(raw.get("registered_actions"))
        resource_types = _string_tuple(raw.get("registered_resource_types"))
        if not actions or not resource_types:
            return None
        return {
            "registered_actions": actions,
            "registered_resource_types": resource_types,
        }

    def _decision(
        self,
        *,
        request: RuntimeActionAuthorizationRequest,
        context: TenantContext,
        correlation_id: str | None,
        now: datetime,
        request_fingerprint: str,
        outcome: RuntimeActionAuthorizationOutcome,
        reason_code: str,
        policy_id: str | None = None,
        policy_version: str | None = None,
        delegation: RuntimeActionDelegation | None = None,
        evaluated_policies: tuple[tuple[str, str], ...] = (),
    ) -> RuntimeActionAuthorizationDecision:
        return RuntimeActionAuthorizationDecision(
            decision_id=self._id_generator(),
            outcome=outcome,
            reason_code=reason_code,
            execution_id=request.execution_id,
            correlation_id=correlation_id,
            action_id=request.action_id,
            resource=request.resource,
            actor_id=context.actor_id,
            idempotency_key=request.idempotency_key,
            request_fingerprint=request_fingerprint,
            decided_at=now,
            expires_at=now + self._decision_ttl,
            policy_id=policy_id,
            policy_version=policy_version,
            delegation_id=delegation.delegation_id if delegation else None,
            delegation_version=delegation.version if delegation else None,
            delegation_digest=delegation.contract_digest if delegation else None,
            tool_arguments_digest=request.tool_arguments_digest,
            evaluated_policies=evaluated_policies,
        )

    def _decision_event(
        self,
        decision: RuntimeActionAuthorizationDecision,
        request: RuntimeActionAuthorizationRequest,
        context: TenantContext,
        fingerprint: str,
    ) -> AgentExecutionEvent:
        return AgentExecutionEvent(
            event_id=decision.decision_id,
            execution_id=decision.execution_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            event_type=EventType.RUNTIME_ACTION_AUTHORIZATION,
            sequence_number=(
                self._event_repository.max_sequence_number(
                    decision.execution_id,
                    context.organization_id,
                    context.project_id,
                )
                + 1
            ),
            occurred_at=decision.decided_at,
            received_at=decision.decided_at,
            correlation_id=decision.correlation_id,
            causation_id=None,
            actor_id=context.actor_id,
            actor_type=ActorType.GOVERNANCE,
            resource_references=(
                f"{decision.resource.resource_type}:{decision.resource.resource_reference}",
            ),
            attributes={
                "authorization_schema_version": decision.schema_version,
                "authorization_outcome": decision.outcome.value,
                "reason_code": decision.reason_code,
                "action_id": decision.action_id,
                "resource_type": decision.resource.resource_type,
                "resource_reference": decision.resource.resource_reference,
                "actor_id": decision.actor_id,
                "policy_id": decision.policy_id,
                "policy_version": decision.policy_version,
                "evaluated_policies": [
                    {"policy_id": policy_id, "version": policy_version}
                    for policy_id, policy_version in decision.evaluated_policies
                ],
                "delegation_id": decision.delegation_id,
                "delegation_version": decision.delegation_version,
                "delegation_digest": decision.delegation_digest,
                "tool_arguments_digest": decision.tool_arguments_digest,
                "expires_at": decision.expires_at.isoformat(),
                "idempotency_key": decision.idempotency_key,
                "request_fingerprint": fingerprint,
                "context_digest": request.context_digest(),
            },
        )

    def _existing_decision(
        self,
        event: AgentExecutionEvent,
        request: RuntimeActionAuthorizationRequest,
        actor_id: str,
        fingerprint: str,
    ) -> RuntimeActionAuthorizationDecision:
        attributes = event.attributes
        if (
            event.event_type is not EventType.RUNTIME_ACTION_AUTHORIZATION
            or attributes.get("request_fingerprint") != fingerprint
        ):
            raise RuntimeActionAuthorizationConflictError(
                "Authorization idempotency key was reused with different input."
            )
        try:
            decision = RuntimeActionAuthorizationDecision(
                decision_id=event.event_id,
                outcome=str(attributes["authorization_outcome"]),
                reason_code=str(attributes["reason_code"]),
                execution_id=event.execution_id,
                correlation_id=event.correlation_id,
                action_id=str(attributes["action_id"]),
                resource=RuntimeActionResource(
                    resource_type=str(attributes["resource_type"]),
                    resource_reference=str(attributes["resource_reference"]),
                ),
                actor_id=str(attributes["actor_id"]),
                idempotency_key=str(attributes["idempotency_key"]),
                request_fingerprint=str(attributes["request_fingerprint"]),
                decided_at=event.occurred_at,
                expires_at=datetime.fromisoformat(str(attributes["expires_at"])),
                policy_id=_optional_string(attributes.get("policy_id")),
                policy_version=_optional_string(attributes.get("policy_version")),
                delegation_id=_optional_string(attributes.get("delegation_id")),
                delegation_version=_optional_string(
                    attributes.get("delegation_version")
                ),
                delegation_digest=_optional_string(attributes.get("delegation_digest")),
                tool_arguments_digest=_optional_string(
                    attributes.get("tool_arguments_digest")
                ),
                evaluated_policies=_evaluated_policies(
                    attributes.get("evaluated_policies")
                ),
                schema_version=str(attributes["authorization_schema_version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeActionAuthorizationPersistenceError(
                "Stored authorization evidence is malformed."
            ) from exc
        if not decision.matches_request(request, actor_id=actor_id):
            raise RuntimeActionAuthorizationConflictError(
                "Authorization idempotency key was reused with different input."
            )
        return decision

    def _resolve_correlation_id(
        self,
        request: RuntimeActionAuthorizationRequest,
        context: TenantContext,
        execution: Any,
    ) -> str | None:
        authoritative = execution.correlation_id or context.correlation_id
        if (
            request.correlation_id is not None
            and authoritative is not None
            and request.correlation_id != authoritative
        ):
            raise RuntimeActionAuthorizationConflictError(
                "Request correlation does not match the authoritative execution."
            )
        return authoritative or request.correlation_id

    def _resolve_delegation(
        self,
        request: RuntimeActionAuthorizationRequest,
        context: TenantContext,
        now: datetime,
    ) -> tuple[RuntimeActionDelegation | None, str | None]:
        if self._delegation_repository is None:
            return None, "DELEGATION_RESOLUTION_UNAVAILABLE"
        if request.delegation_id is None:
            return None, "MISSING_DELEGATION"
        try:
            delegation = self._delegation_repository.get(
                request.delegation_id,
                context.organization_id,
                context.project_id,
            )
        except Exception:  # noqa: BLE001 - trusted state must be resolvable.
            return None, "DELEGATION_RESOLUTION_UNAVAILABLE"
        if delegation is None:
            return None, "DELEGATION_NOT_FOUND"
        if (
            delegation.version != request.delegation_version
            or delegation.contract_digest != request.delegation_digest
        ):
            return None, "DELEGATION_BINDING_MISMATCH"
        if delegation.status.value == "REVOKED":
            return None, "DELEGATION_REVOKED"
        if delegation.expires_at <= now:
            return None, "DELEGATION_EXPIRED"
        if not delegation.permits(
            actor_id=context.actor_id,
            execution_id=request.execution_id,
            action_id=request.action_id,
            resource_type=request.resource.resource_type,
            resource_reference=request.resource.resource_reference,
            now=now,
        ):
            return None, "DELEGATION_SCOPE_DENIED"
        return delegation, None

    @staticmethod
    def _event_idempotency_key(idempotency_key: str) -> str:
        return f"{_EVENT_IDEMPOTENCY_PREFIX}{idempotency_key}"

    @staticmethod
    def _in_scope(definition: PolicyDefinition, context: TenantContext) -> bool:
        return (
            definition.organization_id == context.organization_id
            and definition.project_id == context.project_id
        )


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    items = tuple(item for item in value if isinstance(item, str) and item.strip())
    return items if len(items) == len(value) and len(set(items)) == len(items) else ()


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _evaluated_policies(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        return ()
    bindings: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError("evaluated_policies must contain policy bindings.")
        policy_id = _optional_string(item.get("policy_id"))
        version = _optional_string(item.get("version"))
        if policy_id is None or version is None:
            raise ValueError("evaluated policy binding is malformed.")
        bindings.append((policy_id, version))
    return tuple(bindings)


def _uses_agent_controlled_context(version: PolicyVersion) -> bool:
    """ALLOW rules may not derive authority from runtime supplied facts."""

    return any(
        rule.effect is PolicyEffect.APPROVE
        and any(
            condition.field_path.startswith(("context.", "agent_context."))
            for condition in rule.conditions
        )
        for rule in version.rules
    )
