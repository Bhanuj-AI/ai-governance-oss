from __future__ import annotations

from collections.abc import Mapping

from ai_governance.decisions import DecisionTargetType, GovernancePolicy, PolicyStatus
from ai_governance.decisions.reasoning_models import GovernanceReasoningRequest
from ai_governance.repositories.policy_administration_repository import (
    PolicyAdministrationRepository,
)
from ai_governance.settings_control.domain import SettingContext


class ConfiguredGovernancePolicyProvider:
    """Resolve persisted governance policy versions using scoped settings."""

    def __init__(
        self, repository: PolicyAdministrationRepository, configuration_service
    ) -> None:
        self._repository = repository
        self._configuration_service = configuration_service

    def get_policies_for_request(
        self, request: GovernanceReasoningRequest
    ) -> tuple[GovernancePolicy, ...]:
        organization_id = str(request.metadata.get("_organization_id", ""))
        project_id = str(request.metadata.get("_project_id", ""))
        context = SettingContext(organization_id or None, project_id or None)
        behavior = str(
            self._configuration_service.get(
                "governance.default_policy_version_behavior", context
            )
        )
        explicit_versions = request.metadata.get("policy_versions", {})
        if not isinstance(explicit_versions, Mapping):
            explicit_versions = {}
        definitions = (
            [
                self._repository.get_definition(policy_id)
                for policy_id in request.policy_ids
            ]
            if request.policy_ids
            else self._repository.list_definitions(
                organization_id=organization_id or None,
                project_id=project_id or None,
            )
        )
        policies: list[GovernancePolicy] = []
        for definition in definitions:
            if definition is None:
                continue
            if organization_id and definition.organization_id != organization_id:
                continue
            if project_id and definition.project_id != project_id:
                continue
            selected = None
            explicit = explicit_versions.get(definition.policy_id)
            if explicit is not None:
                selected = self._repository.get_version(
                    definition.policy_id, str(explicit)
                )
            elif behavior == "active":
                selected = self._repository.get_active_version(definition.policy_id)
            elif behavior == "latest":
                candidates = [
                    item
                    for item in self._repository.list_versions(definition.policy_id)
                    if item.status is not PolicyStatus.ARCHIVED
                ]
                selected = max(
                    candidates, key=lambda item: item.created_at, default=None
                )
            if selected is None:
                continue
            policy = selected.to_governance_policy(definition)
            if request.target_type in policy.target_types:
                policies.append(policy)
        return tuple(sorted(policies, key=lambda item: (item.policy_id, item.version)))

    def get_policies_for_target(
        self,
        target_type: DecisionTargetType,
        policy_ids: tuple[str, ...] = (),
    ) -> tuple[GovernancePolicy, ...]:
        # Compatibility path for callers that do not carry tenant metadata.
        return ()
