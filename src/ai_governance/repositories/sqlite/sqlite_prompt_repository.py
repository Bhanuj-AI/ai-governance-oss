from __future__ import annotations

from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.prompts import Prompt
from ai_governance.repositories.mappers.prompt_persistence_mapper import (
    PromptPersistenceMapper,
)
from ai_governance.repositories.prompt_repository import PromptRepository


@final
class SQLitePromptRepository(PromptRepository):
    """
    SQLite implementation of the PromptRepository contract.
    """

    _INSERT_PROMPT_SQL = """
    INSERT OR REPLACE INTO prompt_registry (
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
        :prompt_id,
        :name,
        :version,
        :template,
        :variables_json,
        :created_at,
        :created_by,
        :status,
        :provenance,
        :source_system,
        :source_reference,
        :content_hash,
        :content_available, :tenant_id, :organization_id, :project_id
    )
    """

    _SELECT_PROMPT_COLUMNS = """
    SELECT
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
    FROM prompt_registry
    """

    def __init__(
        self,
        database: SQLiteDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        prompt: Prompt,
    ) -> None:
        record = PromptPersistenceMapper.to_persistence_record(prompt)

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
                f"{self._SELECT_PROMPT_COLUMNS} WHERE prompt_id = ? AND organization_id = ? AND project_id = ?",
                (prompt_id, organization_id, project_id),
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
                "WHERE name = ? AND organization_id = ? AND project_id = ? ORDER BY created_at, version",
                (name, organization_id, project_id),
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
                "WHERE name = ? AND version = ? AND organization_id = ? AND project_id = ?",
                (name, version, organization_id, project_id),
            ).fetchone()

        if row is None:
            return None

        return PromptPersistenceMapper.from_persistence_record(row)

    def find_all(self, organization_id: str = "org_default", project_id: str = "project_default") -> list[Prompt]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_PROMPT_COLUMNS} WHERE organization_id = ? AND project_id = ? ORDER BY name, created_at, version",
                (organization_id, project_id),
            ).fetchall()

        return PromptPersistenceMapper.from_persistence_records(rows)
