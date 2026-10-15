"""Map runtime action authorization results to public transport models."""

from __future__ import annotations

from ai_governance.api.models.runtime_action_authorization import (
    RuntimeActionAuthorizationResponse,
    RuntimeActionResourceResponse,
)
from ai_governance.runtime_authorization import RuntimeActionAuthorizationDecision


class RuntimeActionAuthorizationApiMapper:
    @staticmethod
    def to_response(
        decision: RuntimeActionAuthorizationDecision,
    ) -> RuntimeActionAuthorizationResponse:
        return RuntimeActionAuthorizationResponse(
            schema_version=decision.schema_version,
            decision_id=decision.decision_id,
            outcome=decision.outcome.value,
            reason_code=decision.reason_code,
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            decision_at=decision.decided_at,
            expires_at=decision.expires_at,
            execution_id=decision.execution_id,
            correlation_id=decision.correlation_id,
            action_id=decision.action_id,
            resource=RuntimeActionResourceResponse(
                resource_type=decision.resource.resource_type,
                resource_reference=decision.resource.resource_reference,
            ),
            actor_id=decision.actor_id,
            idempotency_key=decision.idempotency_key,
            request_fingerprint=decision.request_fingerprint,
            delegation_id=decision.delegation_id,
            delegation_version=decision.delegation_version,
            delegation_digest=decision.delegation_digest,
            tool_arguments_digest=decision.tool_arguments_digest,
            evaluated_policies=[
                {"policy_id": policy_id, "version": policy_version}
                for policy_id, policy_version in decision.evaluated_policies
            ],
        )
