from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.transactions import ConnectionTransactionContext, TransactionContext

from .domain import (
    RuntimeSetting,
    SettingAuditRecord,
    SettingScope,
    SettingVersionConflict,
)


class SettingsRepository(Protocol):
    def get(
        self, key: str, scope: SettingScope, scope_id: str
    ) -> RuntimeSetting | None: ...
    def list(self) -> list[RuntimeSetting]: ...
    def save(
        self,
        key: str,
        scope: SettingScope,
        scope_id: str,
        value: Any,
        actor_id: str,
        reason: str,
        expected_version: int,
        transaction: TransactionContext | None = None,
    ) -> RuntimeSetting: ...
    def list_audit(
        self,
        key: str | None = None,
        scope: SettingScope | None = None,
        scope_id: str | None = None,
    ) -> list[SettingAuditRecord]: ...


class InMemorySettingsRepository:
    def __init__(self) -> None:
        self._values: dict[tuple[str, SettingScope, str], RuntimeSetting] = {}
        self._audit: list[SettingAuditRecord] = []
        self._lock = RLock()

    def get(
        self, key: str, scope: SettingScope = SettingScope.SYSTEM, scope_id: str = ""
    ) -> RuntimeSetting | None:
        return self._values.get((key, scope, scope_id))

    def list(self) -> list[RuntimeSetting]:
        return list(self._values.values())

    def save(
        self,
        key: str,
        scope: SettingScope,
        scope_id: str,
        value: Any,
        actor_id: str,
        reason: str,
        expected_version: int,
        transaction: TransactionContext | None = None,
    ) -> RuntimeSetting:
        with self._lock:
            identity = (key, scope, scope_id)
            old = self._values.get(identity)
            current_version = old.version if old else 0
            if current_version != expected_version:
                raise SettingVersionConflict(key, expected_version, current_version)
            now = datetime.now(UTC)
            item = RuntimeSetting(
                key, scope, scope_id, value, current_version + 1, actor_id, now
            )
            self._values[identity] = item
            self._audit.append(
                SettingAuditRecord(
                    str(uuid4()),
                    key,
                    scope,
                    scope_id,
                    old.value if old else None,
                    value,
                    actor_id,
                    reason,
                    item.version,
                    now,
                )
            )
            return item

    def list_audit(
        self,
        key: str | None = None,
        scope: SettingScope | None = None,
        scope_id: str | None = None,
    ) -> list[SettingAuditRecord]:
        return [
            item
            for item in reversed(self._audit)
            if (key is None or item.key == key)
            and (scope is None or item.scope is scope)
            and (scope_id is None or item.scope_id == scope_id)
        ]


class SQLiteSettingsRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database
        self.database.initialize()

    def get(
        self, key: str, scope: SettingScope = SettingScope.SYSTEM, scope_id: str = ""
    ) -> RuntimeSetting | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_setting WHERE key=? AND scope_type=? AND scope_id=?",
                (key, scope.value, scope_id),
            ).fetchone()
        return self._setting(row) if row else None

    def list(self) -> list[RuntimeSetting]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_setting ORDER BY key,scope_type,scope_id"
            ).fetchall()
        return [self._setting(row) for row in rows]

    def save(
        self,
        key: str,
        scope: SettingScope,
        scope_id: str,
        value: Any,
        actor_id: str,
        reason: str,
        expected_version: int,
        transaction: TransactionContext | None = None,
    ) -> RuntimeSetting:
        if transaction is not None:
            raise ValueError("SQLite settings do not support a shared transaction context.")
        now = datetime.now(UTC)
        encoded = json.dumps(value, sort_keys=True)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM runtime_setting WHERE key=? AND scope_type=? AND scope_id=?",
                (key, scope.value, scope_id),
            ).fetchone()
            old = self._setting(row) if row else None
            current_version = old.version if old else 0
            if current_version != expected_version:
                raise SettingVersionConflict(key, expected_version, current_version)
            version = current_version + 1
            connection.execute(
                "INSERT INTO runtime_setting(key,scope_type,scope_id,value_json,version,updated_by,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(key,scope_type,scope_id) DO UPDATE SET value_json=excluded.value_json,version=excluded.version,updated_by=excluded.updated_by,updated_at=excluded.updated_at",
                (
                    key,
                    scope.value,
                    scope_id,
                    encoded,
                    version,
                    actor_id,
                    now.isoformat(),
                ),
            )
            connection.execute(
                "INSERT INTO setting_audit(audit_id,key,scope_type,scope_id,old_value_json,new_value_json,actor_id,reason,version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    key,
                    scope.value,
                    scope_id,
                    json.dumps(old.value) if old else None,
                    encoded,
                    actor_id,
                    reason,
                    version,
                    now.isoformat(),
                ),
            )
            connection.commit()
        return RuntimeSetting(key, scope, scope_id, value, version, actor_id, now)

    def list_audit(
        self,
        key: str | None = None,
        scope: SettingScope | None = None,
        scope_id: str | None = None,
    ) -> list[SettingAuditRecord]:
        clauses: list[str] = []
        parameters: list[str] = []
        if key is not None:
            clauses.append("key=?")
            parameters.append(key)
        if scope is not None:
            clauses.append("scope_type=?")
            parameters.append(scope.value)
        if scope_id is not None:
            clauses.append("scope_id=?")
            parameters.append(scope_id)
        query = (
            "SELECT * FROM setting_audit"
            + (" WHERE " + " AND ".join(clauses) if clauses else "")
            + " ORDER BY created_at DESC"
        )
        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [
            SettingAuditRecord(
                row["audit_id"],
                row["key"],
                SettingScope(row["scope_type"]),
                row["scope_id"],
                json.loads(row["old_value_json"]) if row["old_value_json"] else None,
                json.loads(row["new_value_json"]),
                row["actor_id"],
                row["reason"],
                row["version"],
                datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    @staticmethod
    def _setting(row) -> RuntimeSetting:
        return RuntimeSetting(
            row["key"],
            SettingScope(row["scope_type"]),
            row["scope_id"],
            json.loads(row["value_json"]),
            row["version"],
            row["updated_by"],
            datetime.fromisoformat(row["updated_at"]),
        )


class PostgresSettingsRepository:
    def __init__(self, dsn: str) -> None:
        from kavach.databases.postgres.database import PostgresDatabase

        self.database = PostgresDatabase(dsn)
        self.database.initialize()

    def get(
        self, key: str, scope: SettingScope = SettingScope.SYSTEM, scope_id: str = ""
    ) -> RuntimeSetting | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_setting WHERE key=%s AND scope_type=%s AND scope_id=%s",
                (key, scope.value, scope_id),
            ).fetchone()
        return self._setting(row) if row else None

    def list(self) -> list[RuntimeSetting]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_setting ORDER BY key,scope_type,scope_id"
            ).fetchall()
        return [self._setting(row) for row in rows]

    def save(
        self,
        key: str,
        scope: SettingScope,
        scope_id: str,
        value: Any,
        actor_id: str,
        reason: str,
        expected_version: int,
        transaction: TransactionContext | None = None,
    ) -> RuntimeSetting:
        if transaction is not None:
            return self._save_on_connection(
                transaction.connection,
                key,
                scope,
                scope_id,
                value,
                actor_id,
                reason,
                expected_version,
            )
        with self.database.connect() as connection:
            saved = self._save_on_connection(
                connection,
                key,
                scope,
                scope_id,
                value,
                actor_id,
                reason,
                expected_version,
            )
            connection.commit()
        return saved

    @contextmanager
    def transaction(self):
        """Yield one PostgreSQL transaction for generic extension participation."""
        with self.database.connect() as connection:
            transaction = ConnectionTransactionContext(connection)
            try:
                yield transaction
            except Exception:
                transaction.rollback()
                raise
            else:
                transaction.commit()

    def _save_on_connection(
        self,
        connection,
        key: str,
        scope: SettingScope,
        scope_id: str,
        value: Any,
        actor_id: str,
        reason: str,
        expected_version: int,
    ) -> RuntimeSetting:
        from psycopg.types.json import Jsonb

        now = datetime.now(UTC)
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (f"{key}:{scope.value}:{scope_id}",),
        )
        row = connection.execute(
            "SELECT * FROM runtime_setting WHERE key=%s AND scope_type=%s AND scope_id=%s FOR UPDATE",
            (key, scope.value, scope_id),
        ).fetchone()
        old = self._setting(row) if row else None
        current_version = old.version if old else 0
        if current_version != expected_version:
            raise SettingVersionConflict(key, expected_version, current_version)
        version = current_version + 1
        connection.execute(
            "INSERT INTO runtime_setting(key,scope_type,scope_id,value_json,version,updated_by,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(key,scope_type,scope_id) DO UPDATE SET value_json=EXCLUDED.value_json,version=EXCLUDED.version,updated_by=EXCLUDED.updated_by,updated_at=EXCLUDED.updated_at",
            (key, scope.value, scope_id, Jsonb(value), version, actor_id, now),
        )
        connection.execute(
            "INSERT INTO setting_audit(audit_id,key,scope_type,scope_id,old_value_json,new_value_json,actor_id,reason,version,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                str(uuid4()),
                key,
                scope.value,
                scope_id,
                Jsonb(old.value) if old else None,
                Jsonb(value),
                actor_id,
                reason,
                version,
                now,
            ),
        )
        return RuntimeSetting(key, scope, scope_id, value, version, actor_id, now)

    def list_audit(
        self,
        key: str | None = None,
        scope: SettingScope | None = None,
        scope_id: str | None = None,
    ) -> list[SettingAuditRecord]:
        clauses: list[str] = []
        parameters: list[str] = []
        if key is not None:
            clauses.append("key=%s")
            parameters.append(key)
        if scope is not None:
            clauses.append("scope_type=%s")
            parameters.append(scope.value)
        if scope_id is not None:
            clauses.append("scope_id=%s")
            parameters.append(scope_id)
        query = (
            "SELECT * FROM setting_audit"
            + (" WHERE " + " AND ".join(clauses) if clauses else "")
            + " ORDER BY created_at DESC"
        )
        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [
            SettingAuditRecord(
                row["audit_id"],
                row["key"],
                SettingScope(row["scope_type"]),
                row["scope_id"],
                row["old_value_json"],
                row["new_value_json"],
                row["actor_id"],
                row["reason"],
                row["version"],
                row["created_at"],
            )
            for row in rows
        ]

    @staticmethod
    def _setting(row) -> RuntimeSetting:
        value = (
            row["value_json"]
            if not isinstance(row["value_json"], str)
            else json.loads(row["value_json"])
        )
        return RuntimeSetting(
            row["key"],
            SettingScope(row["scope_type"]),
            row["scope_id"],
            value,
            row["version"],
            row["updated_by"],
            row["updated_at"],
        )
