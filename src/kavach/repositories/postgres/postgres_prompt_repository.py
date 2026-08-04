from __future__ import annotations

from typing import final

from kavach.databases.postgres.database import PostgresDatabase
from kavach.domain.prompts import Prompt
from kavach.repositories.mappers.prompt_persistence_mapper import (
    PromptPersistenceMapper,
)
from kavach.repositories.postgres._record_adapter import with_jsonb_fields
from kavach.repositories.prompt_repository import PromptRepository


@final
class PostgresPromptRepository(PromptRepository):
    """
    PostgreSQL implementation of the PromptRepository contract.
    """

    _INSERT_PROMPT_SQL = """
    INSERT INTO prompt_registry (
        prompt_id,
        name,
        version,
        template,
        variables_json,
        created_at,
        created_by,
        status,
        provenance,
        source_system,
        source_reference,
        content_hash,
        content_available, tenant_id, organization_id, project_id
    )
    VALUES (
        %(prompt_id)s,
        %(name)s,
        %(version)s,
        %(template)s,
        %(variables_json)s,
        %(created_at)s,
        %(created_by)s,
        %(status)s,
        %(provenance)s,
        %(source_system)s,
        %(source_reference)s,
        %(content_hash)s,
        %(content_available)s, %(tenant_id)s, %(organization_id)s, %(project_id)s
    )
    ON CONFLICT (prompt_id)
    DO UPDATE SET
        name = EXCLUDED.name,
        version = EXCLUDED.version,
        template = EXCLUDED.template,
        variables_json = EXCLUDED.variables_json,
        created_at = EXCLUDED.created_at,
        created_by = EXCLUDED.created_by,
        status = EXCLUDED.status,
        provenance = EXCLUDED.provenance,
        source_system = EXCLUDED.source_system,
        source_reference = EXCLUDED.source_reference,
        content_hash = EXCLUDED.content_hash,
        content_available = EXCLUDED.content_available
        , tenant_id = EXCLUDED.tenant_id
        , organization_id = EXCLUDED.organization_id
        , project_id = EXCLUDED.project_id
    """

    _SELECT_PROMPT_COLUMNS = """
    SELECT
        prompt_id,
        name,
        version,
        template,
        variables_json::text AS variables_json,
        created_at::text AS created_at,
        created_by,
        status,
        provenance,
        source_system,
        source_reference,
        content_hash,
        content_available, tenant_id, organization_id, project_id
    FROM prompt_registry
    """

    def __init__(
        self,
        database: PostgresDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        prompt: Prompt,
    ) -> None:
        record = with_jsonb_fields(
            PromptPersistenceMapper.to_persistence_record(prompt),
            "variables_json",
        )

        with self._database.connect() as connection:
            try:
                connection.execute(
                    self._INSERT_PROMPT_SQL,
                    record,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        prompt_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Prompt | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_PROMPT_COLUMNS} "
                "WHERE prompt_id = %(prompt_id)s AND organization_id = %(organization_id)s AND project_id = %(project_id)s",
                {"prompt_id": prompt_id, "organization_id": organization_id, "project_id": project_id},
            ).fetchone()

        if row is None:
            return None

        return PromptPersistenceMapper.from_persistence_record(row)

    def find_by_name(
        self,
        name: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[Prompt]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_PROMPT_COLUMNS} "
                "WHERE name = %(name)s AND organization_id = %(organization_id)s AND project_id = %(project_id)s ORDER BY created_at, version",
                {"name": name, "organization_id": organization_id, "project_id": project_id},
            ).fetchall()

        return PromptPersistenceMapper.from_persistence_records(rows)

    def find_by_name_and_version(
        self,
        name: str,
        version: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Prompt | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_PROMPT_COLUMNS} "
                "WHERE name = %(name)s AND version = %(version)s AND organization_id = %(organization_id)s AND project_id = %(project_id)s",
                {"name": name, "version": version, "organization_id": organization_id, "project_id": project_id},
            ).fetchone()

        if row is None:
            return None

        return PromptPersistenceMapper.from_persistence_record(row)

    def find_all(self, organization_id: str = "org_default", project_id: str = "project_default") -> list[Prompt]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_PROMPT_COLUMNS} "
                "WHERE organization_id = %(organization_id)s AND project_id = %(project_id)s ORDER BY name, created_at, version",
                {"organization_id": organization_id, "project_id": project_id},
            ).fetchall()

        return PromptPersistenceMapper.from_persistence_records(rows)
