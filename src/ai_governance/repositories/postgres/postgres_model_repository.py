from __future__ import annotations

from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.models import Model
from ai_governance.repositories.mappers.model_persistence_mapper import (
    ModelPersistenceMapper,
)
from ai_governance.repositories.model_repository import ModelRepository
from ai_governance.repositories.postgres._record_adapter import with_jsonb_fields


@final
class PostgresModelRepository(ModelRepository):
    """
    PostgreSQL implementation of the ModelRepository contract.
    """

    _INSERT_MODEL_SQL = """
    INSERT INTO model_registry (
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
        %(model_id)s,
        %(provider)s,
        %(model_name)s,
        %(version)s,
        %(parameters_json)s,
        %(cost_json)s,
        %(latency)s,
        %(context_window)s,
        %(creator)s,
        %(created_at)s,
        %(status)s,
        %(provenance)s,
        %(source_system)s,
        %(source_reference)s, %(tenant_id)s, %(organization_id)s, %(project_id)s
    )
    ON CONFLICT (model_id)
    DO UPDATE SET
        provider = EXCLUDED.provider,
        model_name = EXCLUDED.model_name,
        version = EXCLUDED.version,
        parameters_json = EXCLUDED.parameters_json,
        cost_json = EXCLUDED.cost_json,
        latency = EXCLUDED.latency,
        context_window = EXCLUDED.context_window,
        creator = EXCLUDED.creator,
        created_at = EXCLUDED.created_at,
        status = EXCLUDED.status,
        provenance = EXCLUDED.provenance,
        source_system = EXCLUDED.source_system,
        source_reference = EXCLUDED.source_reference
        , tenant_id = EXCLUDED.tenant_id
        , organization_id = EXCLUDED.organization_id
        , project_id = EXCLUDED.project_id
    """

    _SELECT_MODEL_COLUMNS = """
    SELECT
        model_id,
        provider,
        model_name,
        version,
        parameters_json::text AS parameters_json,
        cost_json::text AS cost_json,
        latency,
        context_window,
        creator,
        created_at::text AS created_at,
        status,
        provenance,
        source_system,
        source_reference, tenant_id, organization_id, project_id
    FROM model_registry
    """

    def __init__(
        self,
        database: PostgresDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        model: Model,
    ) -> None:
        record = with_jsonb_fields(
            ModelPersistenceMapper.to_persistence_record(model),
            "parameters_json",
            "cost_json",
        )

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
                f"{self._SELECT_MODEL_COLUMNS} WHERE model_id = %(model_id)s AND organization_id = %(organization_id)s AND project_id = %(project_id)s",
                {"model_id": model_id, "organization_id": organization_id, "project_id": project_id},
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
                "WHERE provider = %(provider)s "
                "AND model_name = %(model_name)s "
                "AND organization_id = %(organization_id)s AND project_id = %(project_id)s "
                "ORDER BY created_at, version",
                {"provider": provider, "model_name": model_name, "organization_id": organization_id, "project_id": project_id},
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
                "WHERE provider = %(provider)s "
                "AND model_name = %(model_name)s "
                "AND version = %(version)s "
                "AND organization_id = %(organization_id)s AND project_id = %(project_id)s",
                {
                    "provider": provider,
                    "model_name": model_name,
                    "version": version,
                    "organization_id": organization_id,
                    "project_id": project_id,
                },
            ).fetchone()

        if row is None:
            return None

        return ModelPersistenceMapper.from_persistence_record(row)

    def find_all(self, organization_id: str = "org_default", project_id: str = "project_default") -> list[Model]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_MODEL_COLUMNS} "
                "WHERE organization_id = %(organization_id)s AND project_id = %(project_id)s ORDER BY provider, model_name, created_at, version",
                {"organization_id": organization_id, "project_id": project_id},
            ).fetchall()

        return ModelPersistenceMapper.from_persistence_records(rows)
