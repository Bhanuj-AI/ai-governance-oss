from __future__ import annotations

from ai_governance.domain.causal_audit import EvidenceInterventionPolicy
from ai_governance.repositories.evidence_intervention_policy_repository import (
    EvidenceInterventionPolicyRepository,
)


class InMemoryEvidenceInterventionPolicyRepository(
    EvidenceInterventionPolicyRepository
):
    def __init__(self) -> None:
        self._items: dict[
            tuple[str, int, str, str | None], EvidenceInterventionPolicy
        ] = {}

    def save(self, policy: EvidenceInterventionPolicy) -> EvidenceInterventionPolicy:
        key = (
            policy.policy_id,
            policy.version,
            policy.organization_id,
            policy.project_id,
        )
        current = self._items.get(key)
        if (
            current is not None
            and current.status.value == "ACTIVE"
            and (
                current.policy_digest != policy.policy_digest
                or policy.status.value not in {"ACTIVE", "RETIRED"}
            )
        ):
            raise ValueError(
                "InterventionPolicyConflict: active policy versions are immutable."
            )
        self._items[key] = policy
        return policy

    def get(
        self, policy_id: str, version: int, organization_id: str, project_id: str | None
    ) -> EvidenceInterventionPolicy | None:
        return self._items.get((policy_id, version, organization_id, project_id))

    def list(
        self, organization_id: str, project_id: str | None
    ) -> list[EvidenceInterventionPolicy]:
        return sorted(
            (
                item
                for item in self._items.values()
                if item.organization_id == organization_id
                and item.project_id == project_id
            ),
            key=lambda item: (item.policy_id, item.version),
        )
