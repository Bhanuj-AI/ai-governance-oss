from __future__ import annotations

import os
import sqlite3
from pathlib import Path


class SQLiteDatabase:
    """
    Lightweight SQLite wrapper responsible only for:

    - opening connections
    - initializing schema
    - transaction management

    Repository classes own all SQL.
    """

    def __init__(self, database_path: Path):

        self._database_path = database_path

    @property
    def database_path(self) -> Path:
        return self._database_path

    def connect(self) -> sqlite3.Connection:

        connection = sqlite3.connect(
            self._database_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )

        connection.row_factory = sqlite3.Row

        return connection

    def initialize(self) -> None:

        schema_path = Path(__file__).parent.joinpath("schema.sql")

        schema = schema_path.read_text(encoding="utf-8")

        with self.connect() as connection:
            self._ensure_settings_scope(connection)
            self._ensure_replay_columns(connection)
            connection.executescript(schema)
            self._ensure_agent_evaluation_columns(connection)
            self._ensure_job_context_column(connection)
            self._ensure_experiment_columns(connection)
            self._ensure_replay_columns(connection)
            self._ensure_tenancy_columns(connection)
            self._ensure_asset_provenance_columns(connection)
            connection.commit()

    @staticmethod
    def _ensure_agent_evaluation_columns(
        connection: sqlite3.Connection,
    ) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(agent_evaluation)"
            ).fetchall()
        }
        expected_columns = {
            "provider_metadata_json": "TEXT",
            "provider_descriptor_snapshot_json": "TEXT",
            "artifacts_json": "TEXT",
            "created_at": "TEXT",
        }

        for column_name, column_type in expected_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    "ALTER TABLE agent_evaluation "
                    f"ADD COLUMN {column_name} {column_type}"
                )

    @staticmethod
    def _ensure_tenancy_columns(connection: sqlite3.Connection) -> None:
        """Idempotently backfill legacy operational tables into bootstrap scope.

        Defaults keep legacy repository inserts compatible while all repositories
        are moved to explicit scope parameters. Control-plane tables themselves
        are excluded because they already define their ownership constraints.
        """
        organization_id = os.getenv("AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_ID", "org_default")
        project_id = os.getenv("AI_GOVERNANCE_BOOTSTRAP_PROJECT_ID", "project_default")
        organization_default = organization_id.replace("'", "''")
        project_default = project_id.replace("'", "''")
        tables = (
            "agent_evaluation",
            "prompt_registry",
            "model_registry",
            "dataset_registry",
            "experiment",
            "experiment_candidate",
            "evaluation_run",
            "leaderboard",
            "job_execution",
            "mcp_execution_audit",
            "ontology_sync_event",
            "governance_decision",
            "governance_decision_audit",
            "policy_version",
            "replay",
        )
        existing_tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in tables:
            if table not in existing_tables:
                continue
            columns = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "organization_id" not in columns:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN organization_id TEXT NOT NULL "
                    f"DEFAULT '{organization_default}'"
                )
            if "project_id" not in columns:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN project_id TEXT NOT NULL "
                    f"DEFAULT '{project_default}'"
                )
            if "tenant_id" not in columns:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL "
                    "DEFAULT 'org_default'"
                )
            connection.execute(
                f"UPDATE {table} SET organization_id=?, project_id=?, tenant_id=? "
                "WHERE organization_id='org_default' AND project_id='project_default'",
                (organization_id, project_id, organization_id),
            )
            connection.execute(
                f"UPDATE {table} SET tenant_id=organization_id WHERE tenant_id='org_default'"
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant "
                f"ON {table}(tenant_id, organization_id, project_id)"
            )
        if "job_execution" in existing_tables:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_execution_tenant_status "
                "ON job_execution(organization_id, project_id, status, created_at)"
            )

    @staticmethod
    def _ensure_asset_provenance_columns(connection: sqlite3.Connection) -> None:
        """Add ownership/source fields to existing asset registry databases."""
        expected = {
            "prompt_registry": {
                "provenance": "TEXT NOT NULL DEFAULT 'MANAGED'",
                "source_system": "TEXT",
                "source_reference": "TEXT",
                "content_hash": "TEXT",
                "content_available": "INTEGER NOT NULL DEFAULT 1",
            },
            "model_registry": {
                "provenance": "TEXT NOT NULL DEFAULT 'MANAGED'",
                "source_system": "TEXT",
                "source_reference": "TEXT",
            },
            "dataset_registry": {
                "provenance": "TEXT NOT NULL DEFAULT 'MANAGED'",
                "source_system": "TEXT",
                "source_reference": "TEXT",
            },
        }
        for table, columns in expected.items():
            table_columns = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if not table_columns:
                continue
            for name, definition in columns.items():
                if name not in table_columns:
                    connection.execute(
                        f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                    )
        SQLiteDatabase._allow_prompt_content_omission(connection)

    @staticmethod
    def _allow_prompt_content_omission(connection: sqlite3.Connection) -> None:
        """Rebuild legacy prompt tables whose template column was NOT NULL.

        Observed producers may deliberately withhold prompt content. SQLite
        cannot remove a ``NOT NULL`` constraint in place, so this is the small
        compatibility migration needed for existing local databases.
        """
        columns = {
            row["name"]: row
            for row in connection.execute("PRAGMA table_info(prompt_registry)").fetchall()
        }
        if not columns or not columns["template"]["notnull"]:
            return
        connection.execute("ALTER TABLE prompt_registry RENAME TO prompt_registry_legacy")
        connection.execute(
            """
            CREATE TABLE prompt_registry (
                prompt_id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                template TEXT,
                variables_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                status TEXT NOT NULL,
                provenance TEXT NOT NULL DEFAULT 'MANAGED',
                source_system TEXT,
                source_reference TEXT,
                content_hash TEXT,
                content_available INTEGER NOT NULL DEFAULT 1,
                tenant_id TEXT NOT NULL DEFAULT 'org_default',
                organization_id TEXT NOT NULL DEFAULT 'org_default',
                project_id TEXT NOT NULL DEFAULT 'project_default',
                UNIQUE (name, version)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO prompt_registry (
                prompt_id, name, version, template, variables_json, created_at,
                created_by, status, provenance, source_system, source_reference,
                content_hash, content_available, tenant_id, organization_id, project_id
            )
            SELECT
                prompt_id, name, version, template, variables_json, created_at,
                created_by, status, provenance, source_system, source_reference,
                content_hash, content_available, tenant_id, organization_id, project_id
            FROM prompt_registry_legacy
            """
        )
        connection.execute("DROP TABLE prompt_registry_legacy")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_prompt_registry_name ON prompt_registry(name)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_prompt_registry_status ON prompt_registry(status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_prompt_registry_tenant "
            "ON prompt_registry(tenant_id, organization_id, project_id)"
        )

    @staticmethod
    def _ensure_job_context_column(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(job_execution)").fetchall()
        }
        if columns and "execution_context_json" not in columns:
            connection.execute(
                "ALTER TABLE job_execution ADD COLUMN execution_context_json TEXT"
            )

    @staticmethod
    def _ensure_experiment_columns(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(experiment)")
        }
        if columns and "updated_at" not in columns:
            connection.execute("ALTER TABLE experiment ADD COLUMN updated_at TEXT")
        if columns:
            connection.execute(
                "UPDATE experiment SET updated_at=created_at "
                "WHERE updated_at IS NULL"
            )

    @staticmethod
    def _ensure_replay_columns(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(replay)")
        }
        for name, type_ in {
            "job_id": "TEXT",
            "replay_execution_id": "TEXT",
            "queued_at": "TEXT",
            "started_at": "TEXT",
            "execution_completed_at": "TEXT",
            "cancel_requested_at": "TEXT",
            "cancelled_at": "TEXT",
            "attempt_count": "INTEGER NOT NULL DEFAULT 0",
            "evaluation_job_id": "TEXT",
            "baseline_evaluation_id": "TEXT",
            "replay_evaluation_id": "TEXT",
            "comparison_id": "TEXT",
            "drift_id": "TEXT",
            "result_id": "TEXT",
            "evaluation_started_at": "TEXT",
            "evaluation_completed_at": "TEXT",
            "comparison_started_at": "TEXT",
            "comparison_completed_at": "TEXT",
            "completed_at": "TEXT",
        }.items():
            if columns and name not in columns:
                connection.execute(f"ALTER TABLE replay ADD COLUMN {name} {type_}")
        if columns:
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_replay_job_id ON replay(job_id)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_replay_execution_id ON replay(replay_execution_id)"
            )
            for column in (
                "evaluation_job_id",
                "baseline_evaluation_id",
                "replay_evaluation_id",
                "comparison_id",
                "drift_id",
                "result_id",
                "completed_at",
            ):
                connection.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_replay_{column} ON replay({column})"
                )

    @staticmethod
    def _ensure_settings_scope(connection: sqlite3.Connection) -> None:
        """Migrate the original global-only settings tables to scoped keys."""
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(runtime_setting)")
        }
        if columns and "scope_type" not in columns:
            connection.execute("ALTER TABLE runtime_setting RENAME TO runtime_setting_global")
            connection.execute(
                "CREATE TABLE runtime_setting (key TEXT NOT NULL, scope_type TEXT NOT NULL, "
                "scope_id TEXT NOT NULL, value_json TEXT NOT NULL, version INTEGER NOT NULL, "
                "updated_by TEXT NOT NULL, updated_at TEXT NOT NULL, "
                "PRIMARY KEY(key, scope_type, scope_id))"
            )
            connection.execute(
                "INSERT INTO runtime_setting SELECT key,'SYSTEM','',value_json,version,updated_by,updated_at "
                "FROM runtime_setting_global"
            )
            connection.execute("DROP TABLE runtime_setting_global")
        audit_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(setting_audit)")
        }
        if audit_columns and "scope_type" not in audit_columns:
            connection.execute("DROP INDEX IF EXISTS idx_setting_audit_key_created")
            connection.execute(
                "ALTER TABLE setting_audit ADD COLUMN scope_type TEXT NOT NULL DEFAULT 'SYSTEM'"
            )
            connection.execute(
                "ALTER TABLE setting_audit ADD COLUMN scope_id TEXT NOT NULL DEFAULT ''"
            )
