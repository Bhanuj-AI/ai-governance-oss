from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from ai_governance.decisions import DecisionTargetType, PolicyEffect, PolicyStatus
from ai_governance.decisions.policy_administration import (
    PolicyDefinition,
    PolicyVersion,
)
from ai_governance.decisions.policy_enums import PolicyCategory
from ai_governance.repositories.policy_administration_repository import (
    PolicyAdministrationConflictError,
    PolicyAdministrationRepository,
)


class InMemoryPolicyAdministrationRepository(
    PolicyAdministrationRepository,
):
    """
    In-memory policy administration store for local Studio workflows.
    """

    def __init__(self) -> None:
        self._definitions: dict[str, PolicyDefinition] = {}
        self._versions: dict[tuple[str, str], PolicyVersion] = {}

    def save_definition(
        self,
        definition: PolicyDefinition,
    ) -> None:
        existing = next(
            (
                item
                for item in self._definitions.values()
                if item.policy_id != definition.policy_id
                and item.project_id == definition.project_id
                and item.name == definition.name
            ),
            None,
        )
        if existing is not None:
            raise PolicyAdministrationConflictError(
                "Policy name must be unique within a project."
            )

        self._definitions[definition.policy_id] = definition

    def get_definition(
        self,
        policy_id: str,
    ) -> PolicyDefinition | None:
        return self._definitions.get(policy_id)

    def list_definitions(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        search: str | None = None,
        owner: str | None = None,
        category: PolicyCategory | str | None = None,
        status: PolicyStatus | str | None = None,
        target_type: DecisionTargetType | str | None = None,
        effect: PolicyEffect | str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PolicyDefinition]:
        normalized_search = search.strip().lower() if search else None
        normalized_category = (
            PolicyCategory(category) if category is not None else None
        )
        normalized_status = PolicyStatus(status) if status is not None else None
        normalized_target_type = (
            DecisionTargetType(target_type) if target_type is not None else None
        )
        normalized_effect = PolicyEffect(effect) if effect is not None else None

        definitions = [
            definition
            for definition in self._definitions.values()
            if organization_id in {None, definition.organization_id}
            and project_id in {None, definition.project_id}
            and owner in {None, definition.owner}
            and normalized_category in {None, definition.category}
            and self._matches_search(definition, normalized_search)
            and self._matches_version_filters(
                definition.policy_id,
                status=normalized_status,
                target_type=normalized_target_type,
                effect=normalized_effect,
            )
        ]
        definitions.sort(key=lambda item: item.created_at, reverse=True)
        if limit is None:
            return definitions[offset:]
        return definitions[offset : offset + limit]

    def save_version(
        self,
        version: PolicyVersion,
    ) -> None:
        key = (version.policy_id, version.version)
        if version.status == PolicyStatus.ACTIVE:
            active = self.get_active_version(version.policy_id)
            if active is not None and active.version != version.version:
                self._versions[(active.policy_id, active.version)] = replace(
                    active,
                    status=PolicyStatus.DEPRECATED,
                    deprecated_at=(
                        version.activated_at
                        or version.created_at
                        or datetime.now(UTC)
                    ),
                )

        self._versions[key] = version

    def get_version(
        self,
        policy_id: str,
        version: str,
    ) -> PolicyVersion | None:
        return self._versions.get((policy_id, version))

    def list_versions(
        self,
        policy_id: str,
    ) -> list[PolicyVersion]:
        versions = [
            version
            for (stored_policy_id, _), version in self._versions.items()
            if stored_policy_id == policy_id
        ]
        return sorted(versions, key=lambda item: _version_sort_key(item.version))

    def get_active_version(
        self,
        policy_id: str,
    ) -> PolicyVersion | None:
        return next(
            (
                version
                for version in self.list_versions(policy_id)
                if version.status == PolicyStatus.ACTIVE
            ),
            None,
        )

    def _matches_version_filters(
        self,
        policy_id: str,
        *,
        status: PolicyStatus | None,
        target_type: DecisionTargetType | None,
        effect: PolicyEffect | None,
    ) -> bool:
        if status is None and target_type is None and effect is None:
            return True

        return any(
            (status is None or version.status == status)
            and (
                target_type is None
                or target_type in version.target_types
            )
            and (
                effect is None
                or any(rule.effect == effect for rule in version.rules)
            )
            for version in self.list_versions(policy_id)
        )

    def _matches_search(
        self,
        definition: PolicyDefinition,
        search: str | None,
    ) -> bool:
        if search is None:
            return True

        haystack = (
            definition.policy_id,
            definition.name,
            definition.description or "",
            definition.owner,
            definition.project_id,
        )
        return any(search in item.lower() for item in haystack)


def _version_sort_key(version: str) -> tuple[int, str]:
    try:
        return (0, f"{int(version):020d}")
    except ValueError:
        return (1, version)
