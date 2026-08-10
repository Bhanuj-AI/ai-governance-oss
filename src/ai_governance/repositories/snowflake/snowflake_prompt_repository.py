from __future__ import annotations

from typing import final

from snowflake.connector import DictCursor

from ai_governance.databases.snowflake.database import SnowflakeDatabase
from ai_governance.domain.prompts import Prompt
from ai_governance.repositories.mappers.prompt_persistence_mapper import (
    PromptPersistenceMapper,
)
from ai_governance.repositories.prompt_repository import PromptRepository
from ai_governance.repositories.snowflake._record_adapter import (
    lowercase_record,
    lowercase_records,
)


@final
class SnowflakePromptRepository(PromptRepository):
    """
    Snowflake implementation of the PromptRepository contract.
    """

    _MERGE_PROMPT_SQL = """
    MERGE INTO prompt_registry target
    USING (
        SELECT
            %(prompt_id)s AS prompt_id,
            %(name)s AS name,
            %(version)s AS version,
            %(template)s AS template,
            PARSE_JSON(%(variables_json)s) AS variables_json,
            TO_TIMESTAMP_TZ(%(created_at)s) AS created_at,
            %(created_by)s AS created_by,
            %(status)s AS status,
            %(provenance)s AS provenance,
            %(source_system)s AS source_system,
            %(source_reference)s AS source_reference,
            %(content_hash)s AS content_hash,
            %(content_available)s AS content_available
    ) source
    ON target.prompt_id = source.prompt_id
    WHEN MATCHED THEN UPDATE SET
        name = source.name,
        version = source.version,
        template = source.template,
        variables_json = source.variables_json,
        created_at = source.created_at,
        created_by = source.created_by,
        status = source.status,
        provenance = source.provenance,
        source_system = source.source_system,
        source_reference = source.source_reference,
        content_hash = source.content_hash,
        content_available = source.content_available
    WHEN NOT MATCHED THEN INSERT (
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
        content_available
    )
    VALUES (
        source.prompt_id,
        source.name,
        source.version,
        source.template,
        source.variables_json,
        source.created_at,
        source.created_by,
        source.status,
        source.provenance,
        source.source_system,
        source.source_reference,
        source.content_hash,
        source.content_available
    )
    """

    _SELECT_PROMPT_COLUMNS = """
    SELECT
        prompt_id,
        name,
        version,
        template,
        TO_JSON(variables_json) AS variables_json,
        TO_VARCHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')
            AS created_at,
        created_by,
        status,
        provenance,
        source_system,
        source_reference,
        content_hash,
        content_available
    FROM prompt_registry
    """

    def __init__(
        self,
        database: SnowflakeDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        prompt: Prompt,
    ) -> None:
        record = PromptPersistenceMapper.to_persistence_record(prompt)

        with self._database.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(self._MERGE_PROMPT_SQL, record)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        prompt_id: str,
    ) -> Prompt | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_PROMPT_COLUMNS} "
                    "WHERE prompt_id = %(prompt_id)s",
                    {"prompt_id": prompt_id},
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return PromptPersistenceMapper.from_persistence_record(
            lowercase_record(row)
        )

    def find_by_name(
        self,
        name: str,
    ) -> list[Prompt]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_PROMPT_COLUMNS} "
                    "WHERE name = %(name)s ORDER BY created_at, version",
                    {"name": name},
                )
                rows = lowercase_records(cursor.fetchall())

        return PromptPersistenceMapper.from_persistence_records(rows)

    def find_by_name_and_version(
        self,
        name: str,
        version: str,
    ) -> Prompt | None:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_PROMPT_COLUMNS} "
                    "WHERE name = %(name)s AND version = %(version)s",
                    {"name": name, "version": version},
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return PromptPersistenceMapper.from_persistence_record(
            lowercase_record(row)
        )

    def find_all(self) -> list[Prompt]:
        with self._database.connect() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    f"{self._SELECT_PROMPT_COLUMNS} "
                    "ORDER BY name, created_at, version"
                )
                rows = lowercase_records(cursor.fetchall())

        return PromptPersistenceMapper.from_persistence_records(rows)
