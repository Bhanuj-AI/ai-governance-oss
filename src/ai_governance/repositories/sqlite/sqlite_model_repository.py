from __future__ import annotations

from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.models import Model
from ai_governance.repositories.mappers.model_persistence_mapper import (
    ModelPersistenceMapper,
)
from ai_governance.repositories.model_repository import ModelRepository


@final
class SQLiteModelRepository(ModelRepository):
    """
    SQLite implementation of the ModelRepository contract.
    """

    _INSERT_MODEL_SQL = """
    INSERT OR REPLACE INTO model_registry (
        model_id,
        provider,
        model_name,
        version,
        parameters_json,
        cost_json,
        latency,
        context_window,
        creator,
        created_at,
        status,
        provenance,
        source_system,
        source_reference, tenant_id, organization_id, project_id
    )
    VALUES (
        :model_id,
        :provider,
        :model_name,
        :version,
        :parameters_json,
        :cost_json,
        :latency,
        :context_window,
        :creator,
        :created_at,
        :status,
        :provenance,
        :source_system,
        :source_reference, :tenant_id, :organization_id, :project_id
    )
    """

    _SELECT_MODEL_COLUMNS = """
    SELECT
        model_id,
        provider,
        model_name,
        version,
        parameters_json,
        cost_json,
        latency,
        context_window,
        creator,
        created_at,
        status,
        provenance,
        source_system,
        source_reference, tenant_id, organization_id, project_id
    FROM model_registry
    """

    def __init__(
        self,
        database: SQLiteDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        model: Model,
    ) -> None:
        record = ModelPersistenceMapper.to_persistence_record(model)

        with self._database.connect() as connection:
            try:
                connection.execute(
                    self._INSERT_MODEL_SQL,
                    record,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        model_id: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Model | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_MODEL_COLUMNS} WHERE model_id = ? AND organization_id = ? AND project_id = ?",
                (model_id, organization_id, project_id),
            ).fetchone()

        if row is None:
            return None

        return ModelPersistenceMapper.from_persistence_record(row)

    def find_by_logical_model(
        self,
        provider: str,
        model_name: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> list[Model]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_MODEL_COLUMNS} "
                "WHERE provider = ? AND model_name = ? AND organization_id = ? AND project_id = ? "
                "ORDER BY created_at, version",
                (provider, model_name, organization_id, project_id),
            ).fetchall()

        return ModelPersistenceMapper.from_persistence_records(rows)

    def find_by_provider_name_and_version(
        self,
        provider: str,
        model_name: str,
        version: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> Model | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_MODEL_COLUMNS} "
                "WHERE provider = ? AND model_name = ? AND version = ? AND organization_id = ? AND project_id = ?",
                (provider, model_name, version, organization_id, project_id),
            ).fetchone()

        if row is None:
            return None

        return ModelPersistenceMapper.from_persistence_record(row)

    def find_all(self, organization_id: str = "org_default", project_id: str = "project_default") -> list[Model]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_MODEL_COLUMNS} "
                "WHERE organization_id = ? AND project_id = ? ORDER BY provider, model_name, created_at, version",
                (organization_id, project_id),
            ).fetchall()

        return ModelPersistenceMapper.from_persistence_records(rows)
