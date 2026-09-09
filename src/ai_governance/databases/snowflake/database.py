from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import snowflake.connector
from snowflake.connector import SnowflakeConnection


@dataclass(frozen=True)
class SnowflakeConnectionConfig:
    account: str
    user: str
    password: str | None
    warehouse: str
    database: str
    schema: str
    role: str | None = None
    authenticator: str | None = None
    private_key: bytes | str | None = None
    token: str | None = None


class SnowflakeDatabase:
    """
    Lightweight Snowflake wrapper responsible only for connection creation
    and schema initialization.
    """

    def __init__(
        self,
        account: str | None = None,
        user: str | None = None,
        password: str | None = None,
        warehouse: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        role: str | None = None,
        authenticator: str | None = None,
        private_key: bytes | str | None = None,
        token: str | None = None,
        config: SnowflakeConnectionConfig | None = None,
    ) -> None:
        self._config = config or SnowflakeConnectionConfig(
            account=self._required(account, "account"),
            user=self._required(user, "user"),
            password=password,
            warehouse=self._required(warehouse, "warehouse"),
            database=self._required(database, "database"),
            schema=self._required(schema, "schema"),
            role=role,
            authenticator=authenticator,
            private_key=private_key,
            token=token,
        )

    @property
    def config(self) -> SnowflakeConnectionConfig:
        return self._config

    def connect(self) -> SnowflakeConnection:
        settings: dict[str, Any] = {
            "account": self._config.account,
            "user": self._config.user,
            "warehouse": self._config.warehouse,
            "database": self._config.database,
            "schema": self._config.schema,
        }

        optional_settings = {
            "password": self._config.password,
            "role": self._config.role,
            "authenticator": self._config.authenticator,
            "private_key": self._config.private_key,
            "token": self._config.token,
        }

        settings.update(
            {
                key: value
                for key, value in optional_settings.items()
                if value is not None
            }
        )

        return snowflake.connector.connect(**settings)

    def initialize(self) -> None:
        schema_path = Path(__file__).parent.joinpath("schema.sql")
        schema = schema_path.read_text(encoding="utf-8")

        with self.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    for statement in self._schema_statements(schema):
                        cursor.execute(statement)
                    cursor.execute(
                        "ALTER TABLE evaluation_run "
                        "ADD COLUMN IF NOT EXISTS failure_reason VARCHAR"
                    )
                    cursor.execute(
                        "ALTER TABLE evaluation_run "
                        "ADD COLUMN IF NOT EXISTS total_item_count NUMBER"
                    )
                    cursor.execute(
                        "ALTER TABLE evaluation_run "
                        "ADD COLUMN IF NOT EXISTS completed_item_count NUMBER NOT NULL DEFAULT 0"
                    )
                    cursor.execute(
                        "ALTER TABLE evaluation_run "
                        "ADD COLUMN IF NOT EXISTS evaluated_item_count NUMBER NOT NULL DEFAULT 0"
                    )
                    cursor.execute(
                        "ALTER TABLE evaluation_run "
                        "ADD COLUMN IF NOT EXISTS runner_provenance_json VARIANT"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _required(
        value: str | None,
        name: str,
    ) -> str:
        if value is None:
            raise ValueError(f"Snowflake {name} is required")

        return value

    @staticmethod
    def _schema_statements(
        schema: str,
    ) -> list[str]:
        return [
            statement.strip()
            for statement in schema.split(";")
            if statement.strip()
        ]
