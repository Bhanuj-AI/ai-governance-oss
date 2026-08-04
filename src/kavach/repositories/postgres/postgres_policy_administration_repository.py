from __future__ import annotations

from datetime import UTC, datetime
from typing import final

import psycopg

from kavach.databases.postgres.database import PostgresDatabase
from kavach.decisions import DecisionTargetType, PolicyEffect, PolicyStatus
from kavach.decisions.policy_administration import (
    PolicyDefinition,
    PolicyVersion,
)
from kavach.decisions.policy_enums import PolicyCategory
from kavach.repositories.mappers.policy_administration_persistence_mapper import (
    PolicyAdministrationPersistenceMapper,
)
from kavach.repositories.policy_administration_repository import (
    PolicyAdministrationConflictError,
    PolicyAdministrationRepository,
)
from kavach.repositories.postgres._record_adapter import with_jsonb_fields


@final
class PostgresPolicyAdministrationRepository(PolicyAdministrationRepository):
    """
    PostgreSQL implementation of the Studio policy administration repository.
    """

    _UPSERT_DEFINITION_SQL = """
    INSERT INTO policy_definition (
        policy_id,
        organization_id,
        project_id,
        name,
        description,
        category,
        owner,
        created_by,
        created_at,
        updated_at,
        metadata_json
    )
    VALUES (
        %(policy_id)s,
        %(organization_id)s,
        %(project_id)s,
        %(name)s,
        %(description)s,
        %(category)s,
        %(owner)s,
        %(created_by)s,
        %(created_at)s,
        %(updated_at)s,
        %(metadata_json)s
    )
    ON CONFLICT (policy_id)
    DO UPDATE SET
        organization_id = EXCLUDED.organization_id,
        project_id = EXCLUDED.project_id,
        name = EXCLUDED.name,
        description = EXCLUDED.description,
        category = EXCLUDED.category,
        owner = EXCLUDED.owner,
        created_by = EXCLUDED.created_by,
        created_at = EXCLUDED.created_at,
        updated_at = EXCLUDED.updated_at,
        metadata_json = EXCLUDED.metadata_json
    """

    _UPSERT_VERSION_SQL = """
    INSERT INTO policy_version (
        policy_id,
        version,
        status,
        target_types_json,
        rules_json,
        created_by,
        created_at,
        activated_at,
        deprecated_at,
        archived_at,
        metadata_json
    )
    VALUES (
        %(policy_id)s,
        %(version)s,
        %(status)s,
        %(target_types_json)s,
        %(rules_json)s,
        %(created_by)s,
        %(created_at)s,
        %(activated_at)s,
        %(deprecated_at)s,
        %(archived_at)s,
        %(metadata_json)s
    )
    ON CONFLICT (policy_id, version)
    DO UPDATE SET
        status = EXCLUDED.status,
        target_types_json = EXCLUDED.target_types_json,
        rules_json = EXCLUDED.rules_json,
        created_by = EXCLUDED.created_by,
        created_at = EXCLUDED.created_at,
        activated_at = EXCLUDED.activated_at,
        deprecated_at = EXCLUDED.deprecated_at,
        archived_at = EXCLUDED.archived_at,
        metadata_json = EXCLUDED.metadata_json
    """

    _SELECT_DEFINITION_COLUMNS = """
    SELECT
        policy_id,
        organization_id,
        project_id,
        name,
        description,
        category,
        owner,
        created_by,
        created_at::text AS created_at,
        updated_at::text AS updated_at,
        metadata_json::text AS metadata_json
    FROM policy_definition
    """

    _SELECT_VERSION_COLUMNS = """
    SELECT
        policy_id,
        version,
        status,
        target_types_json::text AS target_types_json,
        rules_json::text AS rules_json,
        created_by,
        created_at::text AS created_at,
        activated_at::text AS activated_at,
        deprecated_at::text AS deprecated_at,
        archived_at::text AS archived_at,
        metadata_json::text AS metadata_json
    FROM policy_version
    """

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save_definition(
        self,
        definition: PolicyDefinition,
    ) -> None:
        record = with_jsonb_fields(
            PolicyAdministrationPersistenceMapper.definition_to_persistence_record(
                definition
            ),
            "metadata_json",
        )
        with self._database.connect() as connection:
            try:
                connection.execute(self._UPSERT_DEFINITION_SQL, record)
                connection.commit()
            except psycopg.errors.UniqueViolation as exc:
                connection.rollback()
                raise PolicyAdministrationConflictError(
                    "Policy name must be unique within a project."
                ) from exc
            except Exception:
                connection.rollback()
                raise

    def get_definition(
        self,
        policy_id: str,
    ) -> PolicyDefinition | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_DEFINITION_COLUMNS} "
                "WHERE policy_id = %(policy_id)s",
                {"policy_id": policy_id},
            ).fetchone()

        if row is None:
            return None
        return (
            PolicyAdministrationPersistenceMapper.definition_from_persistence_record(
                row
            )
        )

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
        where: list[str] = []
        params: dict[str, str] = {}
        if organization_id is not None:
            where.append("organization_id = %(organization_id)s")
            params["organization_id"] = organization_id
        if project_id is not None:
            where.append("project_id = %(project_id)s")
            params["project_id"] = project_id
        if owner is not None:
            where.append("owner = %(owner)s")
            params["owner"] = owner
        if category is not None:
            where.append("category = %(category)s")
            params["category"] = PolicyCategory(category).value
        if search:
            where.append(
                "("
                "lower(policy_id) LIKE %(search)s OR "
                "lower(name) LIKE %(search)s OR "
                "lower(coalesce(description, '')) LIKE %(search)s OR "
                "lower(owner) LIKE %(search)s OR "
                "lower(project_id) LIKE %(search)s"
                ")"
            )
            params["search"] = f"%{search.strip().lower()}%"

        query = self._SELECT_DEFINITION_COLUMNS
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY created_at DESC, policy_id DESC"

        with self._database.connect() as connection:
            rows = connection.execute(query, params).fetchall()

        definitions = (
            PolicyAdministrationPersistenceMapper.definitions_from_persistence_records(
                rows
            )
        )
        filtered = [
            definition
            for definition in definitions
            if self._matches_version_filters(
                definition.policy_id,
                status=status,
                target_type=target_type,
                effect=effect,
            )
        ]
        if limit is None:
            return filtered[offset:]
        return filtered[offset : offset + limit]

    def save_version(
        self,
        version: PolicyVersion,
    ) -> None:
        record = with_jsonb_fields(
            PolicyAdministrationPersistenceMapper.version_to_persistence_record(
                version
            ),
            "target_types_json",
            "rules_json",
            "metadata_json",
        )
        with self._database.connect() as connection:
            try:
                if version.status == PolicyStatus.ACTIVE:
                    connection.execute(
                        "UPDATE policy_version "
                        "SET status = %(deprecated_status)s, "
                        "deprecated_at = coalesce(deprecated_at, %(deprecated_at)s) "
                        "WHERE policy_id = %(policy_id)s "
                        "AND version <> %(version)s "
                        "AND status = %(active_status)s",
                        {
                            "deprecated_status": PolicyStatus.DEPRECATED.value,
                            "deprecated_at": _deprecation_time(version),
                            "policy_id": version.policy_id,
                            "version": version.version,
                            "active_status": PolicyStatus.ACTIVE.value,
                        },
                    )
                connection.execute(self._UPSERT_VERSION_SQL, record)
                connection.commit()
            except psycopg.errors.UniqueViolation as exc:
                connection.rollback()
                raise PolicyAdministrationConflictError(
                    "Policy version could not be persisted."
                ) from exc
            except Exception:
                connection.rollback()
                raise

    def get_version(
        self,
        policy_id: str,
        version: str,
    ) -> PolicyVersion | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_VERSION_COLUMNS} "
                "WHERE policy_id = %(policy_id)s AND version = %(version)s",
                {"policy_id": policy_id, "version": version},
            ).fetchone()

        if row is None:
            return None
        return PolicyAdministrationPersistenceMapper.version_from_persistence_record(
            row
        )

    def list_versions(
        self,
        policy_id: str,
    ) -> list[PolicyVersion]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_VERSION_COLUMNS} "
                "WHERE policy_id = %(policy_id)s",
                {"policy_id": policy_id},
            ).fetchall()

        versions = (
            PolicyAdministrationPersistenceMapper.versions_from_persistence_records(
                rows
            )
        )
        return sorted(versions, key=lambda item: _version_sort_key(item.version))

    def get_active_version(
        self,
        policy_id: str,
    ) -> PolicyVersion | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_VERSION_COLUMNS} "
                "WHERE policy_id = %(policy_id)s AND status = %(status)s",
                {"policy_id": policy_id, "status": PolicyStatus.ACTIVE.value},
            ).fetchone()

        if row is None:
            return None
        return PolicyAdministrationPersistenceMapper.version_from_persistence_record(
            row
        )

    def _matches_version_filters(
        self,
        policy_id: str,
        *,
        status: PolicyStatus | str | None,
        target_type: DecisionTargetType | str | None,
        effect: PolicyEffect | str | None,
    ) -> bool:
        normalized_status = PolicyStatus(status) if status is not None else None
        normalized_target_type = (
            DecisionTargetType(target_type) if target_type is not None else None
        )
        normalized_effect = PolicyEffect(effect) if effect is not None else None
        if (
            normalized_status is None
            and normalized_target_type is None
            and normalized_effect is None
        ):
            return True

        return any(
            (normalized_status is None or version.status == normalized_status)
            and (
                normalized_target_type is None
                or normalized_target_type in version.target_types
            )
            and (
                normalized_effect is None
                or any(rule.effect == normalized_effect for rule in version.rules)
            )
            for version in self.list_versions(policy_id)
        )


def _deprecation_time(version: PolicyVersion) -> str:
    return (version.activated_at or version.created_at or datetime.now(UTC)).isoformat()


def _version_sort_key(version: str) -> tuple[int, str]:
    try:
        return (0, f"{int(version):020d}")
    except ValueError:
        return (1, version)
