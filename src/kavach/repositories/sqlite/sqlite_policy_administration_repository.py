from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import final

from kavach.databases.sqlite.database import SQLiteDatabase
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


@final
class SQLitePolicyAdministrationRepository(PolicyAdministrationRepository):
    """
    SQLite implementation of the Studio policy administration repository.
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
        :policy_id,
        :organization_id,
        :project_id,
        :name,
        :description,
        :category,
        :owner,
        :created_by,
        :created_at,
        :updated_at,
        :metadata_json
    )
    ON CONFLICT(policy_id)
    DO UPDATE SET
        organization_id = excluded.organization_id,
        project_id = excluded.project_id,
        name = excluded.name,
        description = excluded.description,
        category = excluded.category,
        owner = excluded.owner,
        created_by = excluded.created_by,
        created_at = excluded.created_at,
        updated_at = excluded.updated_at,
        metadata_json = excluded.metadata_json
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
        :policy_id,
        :version,
        :status,
        :target_types_json,
        :rules_json,
        :created_by,
        :created_at,
        :activated_at,
        :deprecated_at,
        :archived_at,
        :metadata_json
    )
    ON CONFLICT(policy_id, version)
    DO UPDATE SET
        status = excluded.status,
        target_types_json = excluded.target_types_json,
        rules_json = excluded.rules_json,
        created_by = excluded.created_by,
        created_at = excluded.created_at,
        activated_at = excluded.activated_at,
        deprecated_at = excluded.deprecated_at,
        archived_at = excluded.archived_at,
        metadata_json = excluded.metadata_json
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
        created_at,
        updated_at,
        metadata_json
    FROM policy_definition
    """

    _SELECT_VERSION_COLUMNS = """
    SELECT
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
    FROM policy_version
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save_definition(
        self,
        definition: PolicyDefinition,
    ) -> None:
        record = (
            PolicyAdministrationPersistenceMapper.definition_to_persistence_record(
                definition
            )
        )
        with self._database.connect() as connection:
            try:
                connection.execute(self._UPSERT_DEFINITION_SQL, record)
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise PolicyAdministrationConflictError(
                    "Policy name must be unique within a project."
                ) from exc

    def get_definition(
        self,
        policy_id: str,
    ) -> PolicyDefinition | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_DEFINITION_COLUMNS} WHERE policy_id = ?",
                (policy_id,),
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
        params: list[str] = []
        if organization_id is not None:
            where.append("organization_id = ?")
            params.append(organization_id)
        if project_id is not None:
            where.append("project_id = ?")
            params.append(project_id)
        if owner is not None:
            where.append("owner = ?")
            params.append(owner)
        if category is not None:
            where.append("category = ?")
            params.append(PolicyCategory(category).value)
        if search:
            where.append(
                "("
                "lower(policy_id) LIKE ? OR "
                "lower(name) LIKE ? OR "
                "lower(coalesce(description, '')) LIKE ? OR "
                "lower(owner) LIKE ? OR "
                "lower(project_id) LIKE ?"
                ")"
            )
            pattern = f"%{search.strip().lower()}%"
            params.extend([pattern, pattern, pattern, pattern, pattern])

        query = self._SELECT_DEFINITION_COLUMNS
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY created_at DESC, policy_id DESC"

        with self._database.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()

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
        record = PolicyAdministrationPersistenceMapper.version_to_persistence_record(
            version
        )
        with self._database.connect() as connection:
            try:
                if version.status == PolicyStatus.ACTIVE:
                    connection.execute(
                        "UPDATE policy_version "
                        "SET status = ?, deprecated_at = coalesce(deprecated_at, ?) "
                        "WHERE policy_id = ? AND version <> ? AND status = ?",
                        (
                            PolicyStatus.DEPRECATED.value,
                            _deprecation_time(version),
                            version.policy_id,
                            version.version,
                            PolicyStatus.ACTIVE.value,
                        ),
                    )
                connection.execute(self._UPSERT_VERSION_SQL, record)
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise PolicyAdministrationConflictError(
                    "Policy version could not be persisted."
                ) from exc

    def get_version(
        self,
        policy_id: str,
        version: str,
    ) -> PolicyVersion | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_VERSION_COLUMNS} "
                "WHERE policy_id = ? AND version = ?",
                (policy_id, version),
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
                f"{self._SELECT_VERSION_COLUMNS} WHERE policy_id = ?",
                (policy_id,),
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
                "WHERE policy_id = ? AND status = ?",
                (policy_id, PolicyStatus.ACTIVE.value),
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
