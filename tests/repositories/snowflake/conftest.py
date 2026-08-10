from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
import snowflake.connector

from ai_governance.databases.snowflake.database import (
    SnowflakeConnectionConfig,
    SnowflakeDatabase,
)


def _snowflake_config(
    schema: str,
) -> SnowflakeConnectionConfig | None:
    required = {
        "account": os.getenv("AI_GOVERNANCE_SNOWFLAKE_ACCOUNT"),
        "user": os.getenv("AI_GOVERNANCE_SNOWFLAKE_USER"),
        "warehouse": os.getenv("AI_GOVERNANCE_SNOWFLAKE_WAREHOUSE"),
        "database": os.getenv("AI_GOVERNANCE_SNOWFLAKE_DATABASE"),
    }

    if not all(required.values()):
        return None

    password = os.getenv("AI_GOVERNANCE_SNOWFLAKE_PASSWORD")
    authenticator = os.getenv("AI_GOVERNANCE_SNOWFLAKE_AUTHENTICATOR")
    token = os.getenv("AI_GOVERNANCE_SNOWFLAKE_TOKEN")
    private_key_path = os.getenv("AI_GOVERNANCE_SNOWFLAKE_PRIVATE_KEY_PATH")
    private_key = (
        Path(private_key_path).read_bytes()
        if private_key_path is not None
        else None
    )

    if not any((password, authenticator, token, private_key)):
        return None

    return SnowflakeConnectionConfig(
        account=required["account"] or "",
        user=required["user"] or "",
        password=password,
        warehouse=required["warehouse"] or "",
        database=required["database"] or "",
        schema=schema,
        role=os.getenv("AI_GOVERNANCE_SNOWFLAKE_ROLE"),
        authenticator=authenticator,
        private_key=private_key,
        token=token,
    )


@pytest.fixture
def snowflake_database() -> Iterator[SnowflakeDatabase]:
    base_schema = os.getenv("AI_GOVERNANCE_SNOWFLAKE_SCHEMA")
    schema_name = f"AI_GOVERNANCE_TEST_{uuid4().hex.upper()}"
    config = _snowflake_config(base_schema or "PUBLIC")

    if config is None:
        pytest.skip("Snowflake credentials are not configured")

    with snowflake.connector.connect(
        **{
            key: value
            for key, value in {
                "account": config.account,
                "user": config.user,
                "password": config.password,
                "warehouse": config.warehouse,
                "database": config.database,
                "schema": config.schema,
                "role": config.role,
                "authenticator": config.authenticator,
                "private_key": config.private_key,
                "token": config.token,
            }.items()
            if value is not None
        }
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA {schema_name}")
        connection.commit()

    database = SnowflakeDatabase(
        config=SnowflakeConnectionConfig(
            account=config.account,
            user=config.user,
            password=config.password,
            warehouse=config.warehouse,
            database=config.database,
            schema=schema_name,
            role=config.role,
            authenticator=config.authenticator,
            private_key=config.private_key,
            token=config.token,
        )
    )
    database.initialize()

    try:
        yield database
    finally:
        with snowflake.connector.connect(
            **{
                key: value
                for key, value in {
                    "account": config.account,
                    "user": config.user,
                    "password": config.password,
                    "warehouse": config.warehouse,
                    "database": config.database,
                    "schema": config.schema,
                    "role": config.role,
                    "authenticator": config.authenticator,
                    "private_key": config.private_key,
                    "token": config.token,
                }.items()
                if value is not None
            }
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name}")
            connection.commit()
