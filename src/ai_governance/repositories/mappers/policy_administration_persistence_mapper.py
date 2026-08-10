from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from ai_governance.decisions import (
    PolicyCondition,
    PolicyRule,
)
from ai_governance.decisions.policy_administration import (
    PolicyDefinition,
    PolicyVersion,
)


class PolicyAdministrationPersistenceMapper:
    """
    Maps Studio policy administration objects to persistence records.
    """

    @staticmethod
    def canonical_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @classmethod
    def definition_to_persistence_record(
        cls,
        definition: PolicyDefinition,
    ) -> dict[str, Any]:
        return {
            "policy_id": definition.policy_id,
            "organization_id": definition.organization_id,
            "project_id": definition.project_id,
            "name": definition.name,
            "description": definition.description,
            "category": definition.category.value,
            "owner": definition.owner,
            "created_by": definition.created_by,
            "created_at": definition.created_at.isoformat(),
            "updated_at": definition.updated_at.isoformat(),
            "metadata_json": cls.canonical_json(definition.metadata),
        }

    @staticmethod
    def definition_from_persistence_record(
        record: Mapping[str, Any],
    ) -> PolicyDefinition:
        return PolicyDefinition(
            policy_id=record["policy_id"],
            organization_id=record["organization_id"],
            project_id=record["project_id"],
            name=record["name"],
            description=record["description"],
            category=record["category"],
            owner=record["owner"],
            created_by=record["created_by"],
            created_at=_datetime_from_value(record["created_at"]),
            updated_at=_datetime_from_value(record["updated_at"]),
            metadata=json.loads(record["metadata_json"]),
        )

    @classmethod
    def definitions_from_persistence_records(
        cls,
        records: Sequence[Mapping[str, Any]],
    ) -> list[PolicyDefinition]:
        return [cls.definition_from_persistence_record(record) for record in records]

    @classmethod
    def version_to_persistence_record(
        cls,
        version: PolicyVersion,
    ) -> dict[str, Any]:
        return {
            "policy_id": version.policy_id,
            "version": version.version,
            "status": version.status.value,
            "target_types_json": cls.canonical_json(
                [target_type.value for target_type in version.target_types]
            ),
            "rules_json": cls.canonical_json(
                [_rule_to_dict(rule) for rule in version.rules]
            ),
            "created_by": version.created_by,
            "created_at": version.created_at.isoformat(),
            "activated_at": _datetime_to_text(version.activated_at),
            "deprecated_at": _datetime_to_text(version.deprecated_at),
            "archived_at": _datetime_to_text(version.archived_at),
            "metadata_json": cls.canonical_json(version.metadata),
        }

    @staticmethod
    def version_from_persistence_record(
        record: Mapping[str, Any],
    ) -> PolicyVersion:
        return PolicyVersion(
            policy_id=record["policy_id"],
            version=record["version"],
            status=record["status"],
            target_types=tuple(json.loads(record["target_types_json"])),
            rules=tuple(
                _rule_from_dict(item)
                for item in json.loads(record["rules_json"])
            ),
            created_by=record["created_by"],
            created_at=_datetime_from_value(record["created_at"]),
            activated_at=_optional_datetime_from_value(record["activated_at"]),
            deprecated_at=_optional_datetime_from_value(record["deprecated_at"]),
            archived_at=_optional_datetime_from_value(record["archived_at"]),
            metadata=json.loads(record["metadata_json"]),
        )

    @classmethod
    def versions_from_persistence_records(
        cls,
        records: Sequence[Mapping[str, Any]],
    ) -> list[PolicyVersion]:
        return [cls.version_from_persistence_record(record) for record in records]


def _rule_to_dict(rule: PolicyRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "name": rule.name,
        "conditions": [
            _condition_to_dict(condition) for condition in rule.conditions
        ],
        "effect": rule.effect.value,
        "reason_template": rule.reason_template,
        "priority": rule.priority,
        "metadata": dict(rule.metadata),
    }


def _rule_from_dict(value: Mapping[str, Any]) -> PolicyRule:
    return PolicyRule(
        rule_id=value["rule_id"],
        name=value["name"],
        conditions=tuple(
            _condition_from_dict(condition)
            for condition in value["conditions"]
        ),
        effect=value["effect"],
        reason_template=value["reason_template"],
        priority=value["priority"],
        metadata=value.get("metadata") or {},
    )


def _condition_to_dict(condition: PolicyCondition) -> dict[str, Any]:
    return {
        "field_path": condition.field_path,
        "operator": condition.operator.value,
        "expected_value": condition.expected_value,
        "metadata": dict(condition.metadata),
    }


def _condition_from_dict(value: Mapping[str, Any]) -> PolicyCondition:
    return PolicyCondition(
        field_path=value["field_path"],
        operator=value["operator"],
        expected_value=value.get("expected_value"),
        metadata=value.get("metadata") or {},
    )


def _datetime_to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime_from_value(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _optional_datetime_from_value(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    return _datetime_from_value(value)
