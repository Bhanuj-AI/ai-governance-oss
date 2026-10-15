"""Public mappings for runtime action delegations."""

from ai_governance.api.models.runtime_action_delegation import (
    RuntimeActionDelegationPermissionResponse,
    RuntimeActionDelegationResponse,
)
from ai_governance.runtime_authorization.delegation import RuntimeActionDelegation


class RuntimeActionDelegationApiMapper:
    @staticmethod
    def to_response(
        delegation: RuntimeActionDelegation,
    ) -> RuntimeActionDelegationResponse:
        return RuntimeActionDelegationResponse(
            schema_version=delegation.schema_version,
            delegation_id=delegation.delegation_id,
            version=delegation.version,
            execution_id=delegation.execution_id,
            issuer_id=delegation.issuer_id,
            runtime_actor_id=delegation.runtime_actor_id,
            permissions=[
                RuntimeActionDelegationPermissionResponse(
                    action_id=item.action_id,
                    resource_type=item.resource_type,
                    resource_references=list(item.resource_references),
                )
                for item in delegation.permissions
            ],
            issued_at=delegation.issued_at,
            expires_at=delegation.expires_at,
            contract_digest=delegation.contract_digest,
            status=delegation.status.value,
            revoked_at=delegation.revoked_at,
            revoked_by=delegation.revoked_by,
            revocation_reference=delegation.revocation_reference,
        )
